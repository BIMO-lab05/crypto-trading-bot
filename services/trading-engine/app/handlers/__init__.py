"""
Endpoint Handlers Package
Extracted from main.py using Strangler Fig pattern

This package contains all HTTP endpoint handlers for the trading-engine service.
Handlers are thin orchestration layers that delegate business logic to service layer.

Architecture:
    Request -> Handler (this package) -> Service Layer -> Domain Logic

Phase 3.1: Added correlation analysis handlers (2025-12-11)
Phase 3.2: Added Kelly position sizing handlers (2025-12-11)
Phase 3.3: Added dynamic risk budget handlers (2025-12-12)
Phase 4.1: Added smart order routing handlers (2025-12-11)
Phase 4.2: Added TWAP/VWAP execution handlers (2025-12-12)
Phase 4.3: Added post-trade analysis handlers (2025-12-12)
Phase 5.1: Added attribution analysis handlers (2025-12-11)
Phase 5.2: Added advanced performance metrics handlers (2025-12-12)
Phase 5.3: Added performance dashboard handlers (2025-12-11)
Phase 9: Added multi-strategy orchestration handlers (2025-12-12)
"""

# Health endpoints
from .health import health_check, get_status, get_detailed_health, readiness_check

# Signal endpoints
from .signals import get_trading_signal, get_enhanced_trading_signal, analyze_and_trade

# Position endpoints
from .positions import get_positions, get_position

# Performance endpoints
from .performance import get_performance

# Trading control endpoints
from .trading_control import start_trading, stop_trading, get_auto_trading_status

# Phase 1 endpoints
from .phase1 import (
    get_phase1_metrics_endpoint,
    get_phase1_health,
    get_latest_phase1_signal,
)

# Trade history endpoints
from .trades import get_trade_history

# Backtesting endpoints
from .backtest import (
    list_strategies,
    run_backtest,
    get_backtest_quick_run,
    compare_strategies,
    get_equity_curve,
    BacktestRequest,
)

# Statistical Arbitrage endpoints (Phase 2.2)
from .statistical_arbitrage import (
    initialize_stat_arb_manager,
    add_pairs_strategy,
    calibrate_pairs_strategy,
    add_funding_strategy,
    setup_triangular_arbitrage,
    generate_signals as generate_stat_arb_signals,
    get_performance as get_stat_arb_performance,
    get_status as get_stat_arb_status,
    reset_manager as reset_stat_arb_manager,
)

# Correlation Analysis endpoints (Phase 3.1)
from .correlation import (
    get_correlation_status,
    get_correlation_matrix,
    get_diversification_score,
    get_pair_correlation,
    get_correlation_alerts,
    check_can_open_position,
    update_correlations,
    initialize_correlation_manager,
)

# Kelly Position Sizing endpoints (Phase 3.2)
from .risk_kelly import (
    router as kelly_router,
    get_kelly_stats,
    calculate_kelly_position,
    simulate_kelly_position,
    record_trade_for_kelly,
    get_kelly_comparison,
    reset_kelly_tracking,
)

# Dynamic Risk Budget endpoints (Phase 3.3)
from .risk_budget import (
    router as risk_budget_router,
    get_current_budget,
    get_risk_utilization,
    get_strategy_allocations,
    set_strategy_allocations,
    calculate_risk_budget,
    adjust_risk_budget,
    get_budget_history,
    get_budget_alerts,
    trigger_emergency,
    clear_emergency,
    reset_budget_manager,
    # Standalone handlers
    get_current_budget_handler,
    get_utilization_handler,
    get_allocation_handler,
    calculate_budget_handler,
    adjust_budget_handler,
    get_history_handler,
)

# Smart Order Routing endpoints (Phase 4.1)
from .execution_router import (
    router as execution_router,
    get_router_stats,
    get_router_status,
    get_order_recommendation,
    analyze_orderbook,
    estimate_slippage,
    get_execution_quality_report,
    reset_router,
)

# TWAP/VWAP Execution endpoints (Phase 4.2)
from .twap_vwap_router import (
    router as twap_vwap_router,
    execute_twap_order,
    execute_vwap_order,
    get_twap_status,
    get_vwap_status,
    get_active_algorithms,
    pause_execution,
    resume_execution,
    cancel_execution,
    get_performance_report,
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    TWAPOrderRequest,
    VWAPOrderRequest,
    ExecutionProgress,
    ExecutionQualityReport,
)

# Post-Trade Analysis endpoints (Phase 4.3)
from .post_trade_router import (
    router as post_trade_router,
    post_trade_router as post_trade_analysis_router,
)

# Attribution Analysis endpoints (Phase 5.1)
from .attribution import (
    router as attribution_router,
    get_attribution_by_strategy,
    get_attribution_by_symbol,
    get_attribution_summary,
    get_attribution_trends,
    get_daily_report as get_attribution_daily_report,
    get_performance_decomposition as get_attribution_decomposition,
)

# Advanced Performance Metrics endpoints (Phase 5.2)
from .analytics import (
    router as analytics_router,
    report_router as analytics_report_router,
    get_risk_adjusted_metrics,
    get_drawdown_metrics,
    get_win_loss_metrics,
    get_risk_metrics,
    get_efficiency_metrics,
    get_all_metrics,
    compare_periods,
    get_benchmark_comparison,
    get_daily_report as get_metrics_daily_report,
    get_monthly_report,
    run_monte_carlo,
)

# Performance Dashboard endpoints (Phase 5.3)
from .performance_dashboard import (
    router as performance_dashboard_router,
    get_performance_dashboard_router,
)

# Multi-Strategy Orchestration endpoints (Phase 9)
from .orchestration import (
    router as orchestration_router,
)

__all__ = [
    # Health
    "health_check",
    "get_status",
    "get_detailed_health",
    # Signals
    "get_trading_signal",
    "get_enhanced_trading_signal",
    "analyze_and_trade",
    # Positions
    "get_positions",
    "get_position",
    # Performance
    "get_performance",
    # Trading Control
    "start_trading",
    "stop_trading",
    "get_auto_trading_status",
    # Phase 1
    "get_phase1_metrics_endpoint",
    "get_phase1_health",
    "get_latest_phase1_signal",
    # Trade History
    "get_trade_history",
    # Backtesting
    "list_strategies",
    "run_backtest",
    "get_backtest_quick_run",
    "compare_strategies",
    "get_equity_curve",
    "BacktestRequest",
    # Statistical Arbitrage (Phase 2.2)
    "initialize_stat_arb_manager",
    "add_pairs_strategy",
    "calibrate_pairs_strategy",
    "add_funding_strategy",
    "setup_triangular_arbitrage",
    "generate_stat_arb_signals",
    "get_stat_arb_performance",
    "get_stat_arb_status",
    "reset_stat_arb_manager",
    # Correlation Analysis (Phase 3.1)
    "get_correlation_status",
    "get_correlation_matrix",
    "get_diversification_score",
    "get_pair_correlation",
    "get_correlation_alerts",
    "check_can_open_position",
    "update_correlations",
    "initialize_correlation_manager",
    # Kelly Position Sizing (Phase 3.2)
    "kelly_router",
    "get_kelly_stats",
    "calculate_kelly_position",
    "simulate_kelly_position",
    "record_trade_for_kelly",
    "get_kelly_comparison",
    "reset_kelly_tracking",
    # Dynamic Risk Budget (Phase 3.3)
    "risk_budget_router",
    "get_current_budget",
    "get_risk_utilization",
    "get_strategy_allocations",
    "set_strategy_allocations",
    "calculate_risk_budget",
    "adjust_risk_budget",
    "get_budget_history",
    "get_budget_alerts",
    "trigger_emergency",
    "clear_emergency",
    "reset_budget_manager",
    "get_current_budget_handler",
    "get_utilization_handler",
    "get_allocation_handler",
    "calculate_budget_handler",
    "adjust_budget_handler",
    "get_history_handler",
    # Smart Order Routing (Phase 4.1)
    "execution_router",
    "get_router_stats",
    "get_router_status",
    "get_order_recommendation",
    "analyze_orderbook",
    "estimate_slippage",
    "get_execution_quality_report",
    "reset_router",
    # TWAP/VWAP Execution (Phase 4.2)
    "twap_vwap_router",
    "execute_twap_order",
    "execute_vwap_order",
    "get_twap_status",
    "get_vwap_status",
    "get_active_algorithms",
    "pause_execution",
    "resume_execution",
    "cancel_execution",
    "get_performance_report",
    "start_scheduler",
    "stop_scheduler",
    "get_scheduler_status",
    "TWAPOrderRequest",
    "VWAPOrderRequest",
    "ExecutionProgress",
    "ExecutionQualityReport",
    # Post-Trade Analysis (Phase 4.3)
    "post_trade_router",
    "post_trade_analysis_router",
    # Attribution Analysis (Phase 5.1)
    "attribution_router",
    "get_attribution_by_strategy",
    "get_attribution_by_symbol",
    "get_attribution_summary",
    "get_attribution_trends",
    "get_attribution_daily_report",
    "get_attribution_decomposition",
    # Advanced Performance Metrics (Phase 5.2)
    "analytics_router",
    "analytics_report_router",
    "get_risk_adjusted_metrics",
    "get_drawdown_metrics",
    "get_win_loss_metrics",
    "get_risk_metrics",
    "get_efficiency_metrics",
    "get_all_metrics",
    "compare_periods",
    "get_benchmark_comparison",
    "get_metrics_daily_report",
    "get_monthly_report",
    "run_monte_carlo",
    # Performance Dashboard (Phase 5.3)
    "performance_dashboard_router",
    "get_performance_dashboard_router",
    # Multi-Strategy Orchestration (Phase 9)
    "orchestration_router",
]
