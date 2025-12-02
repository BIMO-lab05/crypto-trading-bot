"""
Endpoint Handlers Package
Extracted from main.py using Strangler Fig pattern

This package contains all HTTP endpoint handlers for the trading-engine service.
Handlers are thin orchestration layers that delegate business logic to service layer.

Architecture:
    Request → Handler (this package) → Service Layer → Domain Logic
"""

# Health endpoints
from .health import health_check, get_status, get_detailed_health

# Signal endpoints
from .signals import get_trading_signal, analyze_and_trade

# Position endpoints
from .positions import get_positions, get_position

# Performance endpoints
from .performance import get_performance

# Trading control endpoints
from .trading_control import (
    start_trading,
    stop_trading,
    get_auto_trading_status
)

# Phase 1 endpoints
from .phase1 import (
    get_phase1_metrics_endpoint,
    get_phase1_health,
    get_latest_phase1_signal
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
    BacktestRequest
)

__all__ = [
    # Health
    "health_check",
    "get_status",
    "get_detailed_health",
    # Signals
    "get_trading_signal",
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
]
