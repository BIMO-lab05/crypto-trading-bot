"""
Prometheus Metrics and Middleware
Extracted from main.py - Responsibility: Application metrics collection and monitoring

Provides:
- HTTP metrics (requests, duration, active requests)
- Data collection metrics (total, records stored)
- External service metrics (Bybit connector, database)
- PrometheusMiddleware for automatic request tracking
"""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge


# ============================================================================
# PROMETHEUS METRICS DEFINITIONS
# ============================================================================

# HTTP request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]
)

http_requests_active = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# Data collection metrics
data_collection_total = Counter(
    'data_collection_total',
    'Total data collection operations',
    ['symbol', 'data_type', 'status']
)

data_records_stored = Counter(
    'data_records_stored_total',
    'Total records stored in database',
    ['symbol', 'data_type']
)

# External service metrics
bybit_connector_calls_total = Counter(
    'bybit_connector_calls_total',
    'Total calls to Bybit Connector',
    ['endpoint', 'status']
)

database_operations_total = Counter(
    'database_operations_total',
    'Total database operations',
    ['operation', 'status']
)


# ============================================================================
# PROMETHEUS MIDDLEWARE
# ============================================================================

class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic Prometheus metrics collection

    Tracks:
    - Active requests (gauge)
    - Request duration (histogram)
    - Total requests by method, endpoint, and status code (counter)
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and collect metrics"""
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Track active requests
        http_requests_active.inc()

        # Record start time
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Record metrics
            duration = time.time() - start_time
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code
            ).inc()

            return response

        finally:
            # Decrement active requests
            http_requests_active.dec()
