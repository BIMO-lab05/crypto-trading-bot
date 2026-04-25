"""
Trading Engine Core Module
Phase 7: High Availability & Monitoring Infrastructure

This module provides core infrastructure components:
- Circuit Breaker: Prevent cascading failures
- Health Checks: Comprehensive health monitoring
- Metrics: Prometheus metrics collection
- Distributed Tracing: OpenTelemetry integration
"""

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    get_circuit_breaker,
    get_all_circuit_breakers,
    CircuitBreakerRegistry,
)

from app.core.health import (
    HealthChecker,
    HealthStatus,
    ComponentHealth,
    SystemHealthReport,
    get_health_checker,
)

from app.core.metrics import (
    MetricsCollector,
    TradingMetrics,
    get_metrics_collector,
)

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
    "CircuitBreakerRegistry",
    # Health
    "HealthChecker",
    "HealthStatus",
    "ComponentHealth",
    "SystemHealthReport",
    "get_health_checker",
    # Metrics
    "MetricsCollector",
    "TradingMetrics",
    "get_metrics_collector",
]
