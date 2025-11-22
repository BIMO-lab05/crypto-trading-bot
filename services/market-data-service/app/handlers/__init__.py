"""
Endpoint Handlers Package
Extracted from main.py using Strangler Fig pattern

This package contains all HTTP endpoint handlers for the market-data-service.
Handlers are thin orchestration layers that delegate to repository and service layers.

Architecture:
    Request → Handler (this package) → Repository/Service → Database/External API

Modules:
- health: Health checks and metrics endpoints
- collection: Data collection endpoints (kline, ticker, bulk)
- query: Data query endpoints (get klines, ticker, latest)
- scheduler: Scheduler control endpoints (start, stop, trigger)
"""

# Health endpoints
from .health import (
    health_check,
    readiness_check,
    metrics_endpoint
)

# Collection endpoints
from .collection import (
    collect_kline_data,
    collect_ticker_data,
    collect_bulk_data
)

# Query endpoints
from .query import (
    get_klines,
    get_ticker,
    get_latest_kline
)

# Scheduler endpoints
from .scheduler import (
    get_scheduler_status_handler,
    start_scheduler_handler,
    stop_scheduler_handler,
    trigger_manual_collection_handler
)

__all__ = [
    # Health
    "health_check",
    "readiness_check",
    "metrics_endpoint",
    # Collection
    "collect_kline_data",
    "collect_ticker_data",
    "collect_bulk_data",
    # Query
    "get_klines",
    "get_ticker",
    "get_latest_kline",
    # Scheduler
    "get_scheduler_status_handler",
    "start_scheduler_handler",
    "stop_scheduler_handler",
    "trigger_manual_collection_handler",
]
