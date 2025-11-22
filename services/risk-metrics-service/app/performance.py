"""
Performance Monitoring and Optimization Utilities
Tracks response times, implements request batching, and monitors resource usage
"""

import time
import asyncio
import logging
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Single performance measurement"""
    endpoint: str
    duration_ms: float
    timestamp: datetime
    status: str = "success"
    cache_hit: bool = False


class PerformanceMonitor:
    """
    Monitor and track service performance metrics
    Provides insights into response times, bottlenecks, and cache effectiveness
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize performance monitor

        Args:
            max_history: Maximum number of metrics to keep in memory
        """
        self.metrics: deque = deque(maxlen=max_history)
        self.endpoint_stats: Dict[str, Dict] = {}

    def record(self, metric: PerformanceMetric):
        """
        Record a performance metric

        Args:
            metric: Performance measurement to record
        """
        self.metrics.append(metric)

        # Update endpoint-specific stats
        if metric.endpoint not in self.endpoint_stats:
            self.endpoint_stats[metric.endpoint] = {
                "count": 0,
                "total_time": 0.0,
                "min_time": float('inf'),
                "max_time": 0.0,
                "errors": 0,
                "cache_hits": 0
            }

        stats = self.endpoint_stats[metric.endpoint]
        stats["count"] += 1
        stats["total_time"] += metric.duration_ms

        if metric.duration_ms < stats["min_time"]:
            stats["min_time"] = metric.duration_ms
        if metric.duration_ms > stats["max_time"]:
            stats["max_time"] = metric.duration_ms

        if metric.status != "success":
            stats["errors"] += 1

        if metric.cache_hit:
            stats["cache_hits"] += 1

    @asynccontextmanager
    async def measure(self, endpoint: str, cache_hit: bool = False):
        """
        Context manager to measure execution time

        Usage:
            async with monitor.measure('/api/v1/risk/scorecard'):
                result = await expensive_operation()

        Args:
            endpoint: Endpoint being measured
            cache_hit: Whether this was served from cache
        """
        start_time = time.perf_counter()
        status = "success"

        try:
            yield
        except Exception as e:
            status = "error"
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000

            metric = PerformanceMetric(
                endpoint=endpoint,
                duration_ms=duration_ms,
                timestamp=datetime.now(),
                status=status,
                cache_hit=cache_hit
            )
            self.record(metric)

            # Log slow requests
            if duration_ms > 500:
                logger.warning(
                    f"SLOW REQUEST: {endpoint} took {duration_ms:.2f}ms (cache_hit={cache_hit})"
                )

    def get_summary(self, last_minutes: Optional[int] = None) -> Dict[str, Any]:
        """
        Get performance summary

        Args:
            last_minutes: Only include metrics from last N minutes (None = all)

        Returns:
            Summary statistics
        """
        if last_minutes:
            cutoff = datetime.now() - timedelta(minutes=last_minutes)
            relevant_metrics = [m for m in self.metrics if m.timestamp >= cutoff]
        else:
            relevant_metrics = list(self.metrics)

        if not relevant_metrics:
            return {"message": "No metrics available"}

        total_requests = len(relevant_metrics)
        total_time = sum(m.duration_ms for m in relevant_metrics)
        avg_time = total_time / total_requests if total_requests > 0 else 0

        cache_hits = sum(1 for m in relevant_metrics if m.cache_hit)
        errors = sum(1 for m in relevant_metrics if m.status != "success")

        # Calculate percentiles
        sorted_times = sorted(m.duration_ms for m in relevant_metrics)
        p50_idx = int(len(sorted_times) * 0.50)
        p95_idx = int(len(sorted_times) * 0.95)
        p99_idx = int(len(sorted_times) * 0.99)

        return {
            "total_requests": total_requests,
            "avg_response_time_ms": round(avg_time, 2),
            "min_response_time_ms": round(min(m.duration_ms for m in relevant_metrics), 2),
            "max_response_time_ms": round(max(m.duration_ms for m in relevant_metrics), 2),
            "p50_response_time_ms": round(sorted_times[p50_idx], 2) if sorted_times else 0,
            "p95_response_time_ms": round(sorted_times[p95_idx], 2) if sorted_times else 0,
            "p99_response_time_ms": round(sorted_times[p99_idx], 2) if sorted_times else 0,
            "cache_hit_rate_pct": round(cache_hits / total_requests * 100, 2) if total_requests > 0 else 0,
            "error_rate_pct": round(errors / total_requests * 100, 2) if total_requests > 0 else 0,
            "time_window_minutes": last_minutes or "all"
        }

    def get_endpoint_stats(self) -> Dict[str, Dict]:
        """
        Get per-endpoint statistics

        Returns:
            Dict mapping endpoint to its stats
        """
        result = {}
        for endpoint, stats in self.endpoint_stats.items():
            if stats["count"] > 0:
                result[endpoint] = {
                    "requests": stats["count"],
                    "avg_time_ms": round(stats["total_time"] / stats["count"], 2),
                    "min_time_ms": round(stats["min_time"], 2),
                    "max_time_ms": round(stats["max_time"], 2),
                    "error_rate_pct": round(stats["errors"] / stats["count"] * 100, 2),
                    "cache_hit_rate_pct": round(stats["cache_hits"] / stats["count"] * 100, 2)
                }
        return result


class RequestBatcher:
    """
    Batch similar requests together for efficient processing
    Reduces duplicate calculations under high load
    """

    def __init__(self, batch_size: int = 10, max_wait_ms: int = 50):
        """
        Initialize request batcher

        Args:
            batch_size: Maximum batch size before processing
            max_wait_ms: Maximum wait time before processing batch
        """
        self.batch_size = batch_size
        self.max_wait_ms = max_wait_ms
        self.pending: Dict[str, List[asyncio.Future]] = {}
        self.locks: Dict[str, asyncio.Lock] = {}

    async def execute(
        self,
        batch_key: str,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute operation with batching

        Args:
            batch_key: Key to identify similar requests
            operation: Async function to execute
            *args, **kwargs: Arguments for operation

        Returns:
            Operation result
        """
        # Create lock for this batch_key if not exists
        if batch_key not in self.locks:
            self.locks[batch_key] = asyncio.Lock()

        async with self.locks[batch_key]:
            # Create future for this request
            future = asyncio.Future()

            # Add to pending batch
            if batch_key not in self.pending:
                self.pending[batch_key] = []

            self.pending[batch_key].append(future)

            # If batch is full or this is first request, process
            if len(self.pending[batch_key]) >= self.batch_size:
                await self._process_batch(batch_key, operation, *args, **kwargs)
            elif len(self.pending[batch_key]) == 1:
                # Start timer for first request
                asyncio.create_task(
                    self._process_after_delay(batch_key, operation, *args, **kwargs)
                )

        # Wait for result
        return await future

    async def _process_after_delay(
        self,
        batch_key: str,
        operation: Callable,
        *args,
        **kwargs
    ):
        """
        Process batch after delay if not already processed

        Args:
            batch_key: Batch identifier
            operation: Operation to execute
            *args, **kwargs: Operation arguments
        """
        await asyncio.sleep(self.max_wait_ms / 1000.0)

        async with self.locks[batch_key]:
            if batch_key in self.pending and self.pending[batch_key]:
                await self._process_batch(batch_key, operation, *args, **kwargs)

    async def _process_batch(
        self,
        batch_key: str,
        operation: Callable,
        *args,
        **kwargs
    ):
        """
        Process all pending requests in batch

        Args:
            batch_key: Batch identifier
            operation: Operation to execute
            *args, **kwargs: Operation arguments
        """
        if batch_key not in self.pending or not self.pending[batch_key]:
            return

        futures = self.pending[batch_key]
        self.pending[batch_key] = []

        logger.debug(f"Processing batch of {len(futures)} requests for {batch_key}")

        try:
            # Execute operation once for the batch
            result = await operation(*args, **kwargs)

            # Set result for all futures
            for future in futures:
                if not future.done():
                    future.set_result(result)

        except Exception as e:
            # Propagate error to all futures
            logger.error(f"Batch processing error for {batch_key}: {e}")
            for future in futures:
                if not future.done():
                    future.set_exception(e)


class ConnectionPool:
    """
    Simple HTTP connection pool for external services
    Reuses connections to reduce overhead
    """

    def __init__(self, max_connections: int = 100, timeout: float = 10.0):
        """
        Initialize connection pool

        Args:
            max_connections: Maximum concurrent connections
            timeout: Request timeout in seconds
        """
        self.max_connections = max_connections
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_connections)
        self.active_connections = 0

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire connection from pool

        Usage:
            async with pool.acquire():
                response = await client.get(url)
        """
        async with self.semaphore:
            self.active_connections += 1
            try:
                yield
            finally:
                self.active_connections -= 1

    def get_stats(self) -> Dict[str, int]:
        """Get pool statistics"""
        return {
            "max_connections": self.max_connections,
            "active_connections": self.active_connections,
            "available_connections": self.max_connections - self.active_connections
        }


# Global instances (initialized in main.py)
performance_monitor: Optional[PerformanceMonitor] = None
request_batcher: Optional[RequestBatcher] = None
connection_pool: Optional[ConnectionPool] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance"""
    global performance_monitor
    if performance_monitor is None:
        performance_monitor = PerformanceMonitor()
    return performance_monitor


def get_request_batcher() -> RequestBatcher:
    """Get global request batcher instance"""
    global request_batcher
    if request_batcher is None:
        request_batcher = RequestBatcher()
    return request_batcher


def get_connection_pool() -> ConnectionPool:
    """Get global connection pool instance"""
    global connection_pool
    if connection_pool is None:
        connection_pool = ConnectionPool()
    return connection_pool
