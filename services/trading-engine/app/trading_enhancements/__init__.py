"""
Trading Enhancements Module
Research-Backed Improvements for Auto Trader (2025-11-30)

Based on comprehensive research into:
- Order Management Systems (OMS)
- Risk Management in Auto Trading
- Signal Processing and Execution
- State Management
- Performance Optimization
- Modern Auto Trading Patterns
- Advanced Position Sizing Algorithms
- Smart Order Execution Strategies
- Performance Analytics and Metrics

Key Components:
- CircuitBreaker: Resilience pattern for API failures
- OrderStateMachine: FIX-protocol style order state management
- KillSwitch: Multi-threshold emergency stop mechanism
- SlippageManager: Dynamic slippage control
- ExecutionTimer: Position monitoring with proper intervals
- AdvancedPositionSizer: Kelly Criterion, Optimal F, ATR-based sizing
- SmartOrderExecutor: TWAP, VWAP, Iceberg, POV algorithms
- PerformanceAnalytics: Sharpe, Sortino, VaR, CVaR metrics
"""

# Core Trading Enhancements
from app.trading_enhancements.circuit_breaker import CircuitBreaker, CircuitState
from app.trading_enhancements.order_state_machine import OrderStateMachine, OrderState
from app.trading_enhancements.kill_switch import KillSwitch, KillSwitchConfig
from app.trading_enhancements.slippage_manager import SlippageManager
from app.trading_enhancements.execution_timer import ExecutionTimer

# Advanced Position Sizing
from app.trading_enhancements.advanced_position_sizing import (
    AdvancedPositionSizer,
    AdvancedSizingMethod,
    AdvancedSizingConfig,
    PositionSizeResult
)

# Smart Order Execution
from app.trading_enhancements.smart_order_execution import (
    SmartOrderExecutor,
    ExecutionAlgorithm,
    ExecutionPlan,
    ExecutionResult,
    OrderSlice
)

# Performance Analytics
from app.trading_enhancements.performance_analytics import (
    PerformanceAnalytics,
    PerformanceReport,
    TradeStatistics,
    RiskMetrics,
    DrawdownInfo,
    RiskMetricMethod
)

__all__ = [
    # Core Enhancements
    "CircuitBreaker",
    "CircuitState",
    "OrderStateMachine",
    "OrderState",
    "KillSwitch",
    "KillSwitchConfig",
    "SlippageManager",
    "ExecutionTimer",
    # Advanced Position Sizing
    "AdvancedPositionSizer",
    "AdvancedSizingMethod",
    "AdvancedSizingConfig",
    "PositionSizeResult",
    # Smart Order Execution
    "SmartOrderExecutor",
    "ExecutionAlgorithm",
    "ExecutionPlan",
    "ExecutionResult",
    "OrderSlice",
    # Performance Analytics
    "PerformanceAnalytics",
    "PerformanceReport",
    "TradeStatistics",
    "RiskMetrics",
    "DrawdownInfo",
    "RiskMetricMethod"
]
