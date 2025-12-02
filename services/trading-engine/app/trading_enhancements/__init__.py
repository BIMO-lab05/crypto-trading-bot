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
- Adaptive Technical Indicators
- Walk Forward Efficiency Testing
- Limit Order Execution Optimization
- Market Regime Detection via Hurst Exponent
- ATR-Based Trailing Stops (2025-12-02)
- Regime-Based Strategy Selection (2025-12-02)
- Partial Profit Taking Scale-Out (2025-12-02)

Key Components:
- CircuitBreaker: Resilience pattern for API failures
- OrderStateMachine: FIX-protocol style order state management
- KillSwitch: Multi-threshold emergency stop mechanism
- SlippageManager: Dynamic slippage control
- ExecutionTimer: Position monitoring with proper intervals
- AdvancedPositionSizer: Kelly Criterion, Optimal F, ATR-based sizing
- SmartOrderExecutor: TWAP, VWAP, Iceberg, POV algorithms
- PerformanceAnalytics: Sharpe, Sortino, VaR, CVaR metrics
- AdaptiveRSI: Volatility-adjusted RSI with dynamic thresholds
- WalkForwardTester: Strategy robustness validation via WFE analysis
- LimitOrderExecutor: Smart limit order execution with fallback
- HurstExponentCalculator: Market regime detection for strategy selection
- ATRTrailingStop: Dynamic trailing stops adapting to market volatility
- RegimeStrategySelector: Hurst-based strategy parameter selection
- PartialProfitTaker: Scale-out at multiple profit levels
- RegimeAdaptiveRSI: Hurst-adjusted RSI thresholds (2025-12-02)
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

# Adaptive RSI Indicator
from app.trading_enhancements.adaptive_rsi import (
    AdaptiveRSI,
    AdaptiveRSIConfig,
    AdaptiveRSIResult,
    RSIThresholds,
    SignalType,
    VolatilityRegime,
    TrendDirection,
    get_adaptive_rsi,
    reset_adaptive_rsi,
    calculate_adaptive_rsi_signal
)

# Walk Forward Efficiency Testing
from app.trading_enhancements.walk_forward_tester import (
    WalkForwardTester,
    WFEConfig,
    WFEStatus,
    WalkForwardResult,
    RobustnessReport,
    TradeData,
    PeriodMetrics,
    get_walk_forward_tester,
    reset_walk_forward_tester
)

# Limit Order Execution
from app.trading_enhancements.limit_order_executor import (
    LimitOrderExecutor,
    LimitOrderConfig,
    LimitOrderResult,
    LimitOrderType,
    FillStatus,
    SlippageSavingsEstimate,
    PartialFillInfo,
    get_limit_order_executor
)

# Hurst Exponent for Market Regime Detection
from app.trading_enhancements.hurst_exponent import (
    HurstExponentCalculator,
    HurstConfig,
    HurstResult,
    MarketRegimeType,
    StrategyType,
    create_hurst_calculator
)

# ATR-Based Trailing Stops
from app.trading_enhancements.atr_trailing_stop import (
    ATRTrailingStop,
    ATRTrailingStopConfig,
    PositionTrailState,
    PositionSide,
    VolatilityRegime as TrailingStopVolatilityRegime,
    get_atr_trailing_stop,
    reset_atr_trailing_stop,
    calculate_trailing_stop_update
)

# Regime-Based Strategy Selection
from app.trading_enhancements.regime_strategy_selector import (
    RegimeStrategySelector,
    RegimeStrategyConfig,
    TradingSignal,
    AdjustedSignal,
    SignalType as RegimeSignalType,
    get_regime_strategy_selector,
    create_regime_strategy_selector
)

# Partial Profit Taking
from app.trading_enhancements.partial_profit_taker import (
    PartialProfitTaker,
    PartialProfitConfig,
    PartialExitStatus,
    PartialExitLevel,
    PartialExitToExecute,
    PositionPartialState,
    get_partial_profit_taker,
    reset_partial_profit_taker
)

# Regime-Adaptive RSI (Hurst + ATR-based thresholds)
from app.trading_enhancements.regime_adaptive_rsi import (
    RegimeAdaptiveRSI,
    RegimeRSIConfig,
    RegimeRSIThresholds,
    RegimeAdaptiveRSIResult,
    RegimeAdjustmentLevel,
    get_regime_adaptive_rsi,
    reset_regime_adaptive_rsi,
    calculate_regime_adaptive_signal
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
    "RiskMetricMethod",
    # Adaptive RSI
    "AdaptiveRSI",
    "AdaptiveRSIConfig",
    "AdaptiveRSIResult",
    "RSIThresholds",
    "SignalType",
    "VolatilityRegime",
    "TrendDirection",
    "get_adaptive_rsi",
    "reset_adaptive_rsi",
    "calculate_adaptive_rsi_signal",
    # Walk Forward Efficiency Testing
    "WalkForwardTester",
    "WFEConfig",
    "WFEStatus",
    "WalkForwardResult",
    "RobustnessReport",
    "TradeData",
    "PeriodMetrics",
    "get_walk_forward_tester",
    "reset_walk_forward_tester",
    # Limit Order Execution
    "LimitOrderExecutor",
    "LimitOrderConfig",
    "LimitOrderResult",
    "LimitOrderType",
    "FillStatus",
    "SlippageSavingsEstimate",
    "PartialFillInfo",
    "get_limit_order_executor",
    # Hurst Exponent / Market Regime Detection
    "HurstExponentCalculator",
    "HurstConfig",
    "HurstResult",
    "MarketRegimeType",
    "StrategyType",
    "create_hurst_calculator",
    # ATR Trailing Stops
    "ATRTrailingStop",
    "ATRTrailingStopConfig",
    "PositionTrailState",
    "PositionSide",
    "TrailingStopVolatilityRegime",
    "get_atr_trailing_stop",
    "reset_atr_trailing_stop",
    "calculate_trailing_stop_update",
    # Regime Strategy Selection
    "RegimeStrategySelector",
    "RegimeStrategyConfig",
    "TradingSignal",
    "AdjustedSignal",
    "RegimeSignalType",
    "get_regime_strategy_selector",
    "create_regime_strategy_selector",
    # Partial Profit Taking
    "PartialProfitTaker",
    "PartialProfitConfig",
    "PartialExitStatus",
    "PartialExitLevel",
    "PartialExitToExecute",
    "PositionPartialState",
    "get_partial_profit_taker",
    "reset_partial_profit_taker",
    # Regime-Adaptive RSI
    "RegimeAdaptiveRSI",
    "RegimeRSIConfig",
    "RegimeRSIThresholds",
    "RegimeAdaptiveRSIResult",
    "RegimeAdjustmentLevel",
    "get_regime_adaptive_rsi",
    "reset_regime_adaptive_rsi",
    "calculate_regime_adaptive_signal"
]
