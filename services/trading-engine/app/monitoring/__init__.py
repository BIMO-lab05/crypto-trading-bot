"""
Monitoring and Alerting Module
Provides Prometheus metrics, health checks, and alerting utilities

REFACTORED: Phase 3 Complete - Modular monitoring system
"""

from .metrics import (
    metrics_middleware,
    http_requests_total,
    http_request_duration,
    active_positions_gauge,
    trading_signals_total,
    trade_executions_total,
    trade_errors_total,
    position_pnl_gauge,
    balance_gauge,
    record_cache_hit,
    record_cache_miss
)
from .alerts import (
    send_slack_alert,
    send_email_alert,
    AlertLevel,
    TradingAlert
)
from .health import (
    HealthMonitor,
    get_health_monitor,
    HealthStatus,
    DependencyHealth,
    SystemHealth
)

__all__ = [
    # Metrics
    'metrics_middleware',
    'http_requests_total',
    'http_request_duration',
    'active_positions_gauge',
    'trading_signals_total',
    'trade_executions_total',
    'trade_errors_total',
    'position_pnl_gauge',
    'balance_gauge',
    'record_cache_hit',
    'record_cache_miss',
    # Alerts
    'send_slack_alert',
    'send_email_alert',
    'AlertLevel',
    'TradingAlert',
    # Health
    'HealthMonitor',
    'get_health_monitor',
    'HealthStatus',
    'DependencyHealth',
    'SystemHealth'
]
