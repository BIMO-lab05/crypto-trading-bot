"""
Utilities Package
Extracted from main.py - Common utilities for market-data-service

Modules:
- logging_config: Structured logging with secret masking
- metrics: Prometheus metrics and middleware
- request_models: API request/response models
"""

from .logging_config import SecretMaskingFormatter, setup_logging
from .metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_active,
    data_collection_total,
    data_records_stored,
    bybit_connector_calls_total,
    database_operations_total,
    PrometheusMiddleware
)
from .request_models import IntervalEnum, CollectKlineRequest, BulkCollectRequest

__all__ = [
    # Logging
    "SecretMaskingFormatter",
    "setup_logging",
    # Metrics
    "http_requests_total",
    "http_request_duration_seconds",
    "http_requests_active",
    "data_collection_total",
    "data_records_stored",
    "bybit_connector_calls_total",
    "database_operations_total",
    "PrometheusMiddleware",
    # Models
    "IntervalEnum",
    "CollectKlineRequest",
    "BulkCollectRequest",
]
