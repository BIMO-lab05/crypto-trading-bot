"""
Monitoring and Alerting Module
Provides Prometheus metrics, health checks, and alerting utilities

REFACTORED: Phase 3 Complete - Modular monitoring system
UPDATED: 2025-12-11 - Added Statistical Arbitrage metrics
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
from .stat_arb_metrics import (
    StatArbMetricsCollector,
    get_metrics_collector,
    update_metrics_from_manager,
    # Manager metrics
    stat_arb_total_capital,
    stat_arb_allocated_capital,
    stat_arb_available_capital,
    stat_arb_total_profit,
    stat_arb_roi_percent,
    stat_arb_total_trades,
    stat_arb_win_rate,
    # Signal metrics
    stat_arb_signals_generated,
    stat_arb_signals_executed,
    stat_arb_signals_rejected,
    # Strategy metrics
    stat_arb_strategy_count,
    stat_arb_strategy_profit,
    # Pairs metrics
    stat_arb_pairs_zscore,
    stat_arb_pairs_spread,
    stat_arb_pairs_cointegration,
    # Funding metrics
    stat_arb_funding_rate,
    stat_arb_funding_annualized_yield,
    # Triangular metrics
    stat_arb_triangular_paths,
    stat_arb_triangular_opportunity,
    stat_arb_triangular_latency_ms
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
    'SystemHealth',
    # Statistical Arbitrage Metrics
    'StatArbMetricsCollector',
    'get_metrics_collector',
    'update_metrics_from_manager',
    'stat_arb_total_capital',
    'stat_arb_allocated_capital',
    'stat_arb_available_capital',
    'stat_arb_total_profit',
    'stat_arb_roi_percent',
    'stat_arb_total_trades',
    'stat_arb_win_rate',
    'stat_arb_signals_generated',
    'stat_arb_signals_executed',
    'stat_arb_signals_rejected',
    'stat_arb_strategy_count',
    'stat_arb_strategy_profit',
    'stat_arb_pairs_zscore',
    'stat_arb_pairs_spread',
    'stat_arb_pairs_cointegration',
    'stat_arb_funding_rate',
    'stat_arb_funding_annualized_yield',
    'stat_arb_triangular_paths',
    'stat_arb_triangular_opportunity',
    'stat_arb_triangular_latency_ms'
]
