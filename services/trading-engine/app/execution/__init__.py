"""
Smart Order Execution Module - Phase 4.1/4.2 Implementation
Purpose: Intelligent order routing and execution optimization for crypto trading

This module provides comprehensive smart order routing capabilities:
- Select optimal order type based on market conditions and urgency
- Analyze order book depth for liquidity assessment
- Estimate and minimize slippage through intelligent routing
- Split large orders using TWAP/VWAP/Iceberg strategies
- Optimize execution fees (maker vs taker)
- Track execution quality metrics
- Algorithmic execution with adaptive scheduling
- Background task management for order slices

Components:
- SmartOrderRouter: Main routing engine integrating all components
- OrderbookAnalyzer: Real-time order book analysis and liquidity scoring
- ExecutionOptimizer: Fee and timing optimization with cost analysis
- TWAPAlgorithm: Time-weighted average price execution
- VWAPAlgorithm: Volume-weighted average price execution
- ExecutionScheduler: Background task management for algorithmic orders
- Legacy SmartRouter: Original implementation (maintained for compatibility)

Architecture:
+------------------+
|  SmartOrderRouter|  <- Main integration layer
+--------+---------+
         |
    +----+----+----------------+-------------+
    |         |                |             |
+---v---+ +---v------+  +------v-------+ +---v----+
|Orderbook| |Execution|  |Legacy Smart  | |TWAP/   |
|Analyzer | |Optimizer|  |Router        | |VWAP    |
+---------+ +----------+  +--------------+ +--------+
                                              |
                                    +---------v----------+
                                    |ExecutionScheduler  |
                                    |Background Tasks    |
                                    +--------------------+

Research Sources:
- Optimal Execution (Almgren-Chriss model)
- Market Impact Analysis (Kyle's Lambda)
- Order Book Dynamics in Crypto Markets
- Maker vs Taker Fee Economics
- VWAP Execution Algorithms (Konishi, 2002)
- Implementation Shortfall Analysis (Perold, 1988)

Phase 4.1: Smart Order Routing (2025-12-11)
Phase 4.2: Enhanced TWAP/VWAP Execution (2025-12-12)

Created: 2025-12-11
Author: Backend Developer Agent
"""

# ============================================================================
# ORDERBOOK ANALYZER - Liquidity analysis and market impact estimation
# ============================================================================
from app.execution.orderbook_analyzer import (
    # Main analyzer
    OrderbookAnalyzer,
    OrderBookConfig,
    # Enumerations
    LiquidityLevel,
    OrderBookState,
    SpreadCategory,
    # Data classes
    PriceLevel,
    DepthAnalysis,
    MarketImpactEstimate,
    LiquidityReport,
    OptimalLimitPrice,
    # Factory functions
    get_orderbook_analyzer,
    reset_orderbook_analyzer,
)

# ============================================================================
# EXECUTION OPTIMIZER - Fee and timing optimization
# ============================================================================
from app.execution.execution_optimizer import (
    # Main optimizer
    ExecutionOptimizer,
    ExecutionOptimizerConfig,
    FeeStructure,
    # Enumerations
    ExecutionUrgency,
    OptimalOrderType,
    TimingStrategy,
    CostComponent,
    # Data classes
    CostBreakdown,
    OptimizationResult,
    ExecutionMetrics,
    # Factory functions
    get_execution_optimizer,
    reset_execution_optimizer,
)

# ============================================================================
# SMART ORDER ROUTER - Main integration component
# ============================================================================
from app.execution.smart_order_router import (
    # Main router
    SmartOrderRouter as SmartOrderRouterV2,
    SmartRouterConfig as SmartRouterConfigV2,
    # Enumerations
    RoutingStrategy,
    ExecutionMode,
    OrderStatus,
    # Data classes
    RoutingDecision,
    ExecutionResult,
    RouterMetrics as RouterMetricsV2,
    # Factory functions
    get_smart_order_router,
    reset_smart_order_router,
)

# ============================================================================
# TWAP/VWAP ALGORITHMS - Algorithmic execution strategies
# ============================================================================
from app.execution.twap_vwap import (
    # Main algorithms
    TWAPAlgorithm,
    VWAPAlgorithm,
    # Configuration
    TWAPConfig,
    VWAPConfig,
    # Enumerations
    ExecutionState,
    AdaptiveMode,
    BenchmarkType,
    # Data classes
    ChunkSchedule,
    ExecutionBenchmark,
    SlippageAlert,
    AlgorithmMetrics,
    # Supporting classes
    SlippageTracker,
    MarketImpactEstimator,
    AlgorithmMetricsAggregator,
    # Factory functions
    create_twap_algorithm,
    create_vwap_algorithm,
    get_twap_algorithm,
    get_vwap_algorithm,
    reset_algorithms,
)

# ============================================================================
# EXECUTION SCHEDULER - Background task management (Phase 4.2)
# ============================================================================
from app.execution.execution_scheduler import (
    # Main scheduler
    ExecutionScheduler,
    # Enumerations
    OrderPriority,
    AlgorithmType,
    SchedulerState,
    OrderLifecycleState,
    # Data classes
    ScheduledOrder,
    ChunkExecution,
    ExecutionReport,
    SchedulerMetrics,
    # Factory functions
    get_execution_scheduler,
    reset_execution_scheduler,
)

# ============================================================================
# LEGACY SMART ROUTER - Original implementation (backward compatibility)
# ============================================================================
from app.execution.smart_router import (
    # Main router (legacy)
    SmartOrderRouter,
    SmartRouterConfig,
    # Enumerations (legacy)
    ExecutionUrgency as LegacyExecutionUrgency,
    ExecutionStrategyType,
    OrderTypeSelection,
    # Data classes (legacy)
    OrderBookLevel,
    OrderBookAnalysis,
    SlippageEstimate,
    OrderTypeRecommendation,
    ExecutionRecord,
    RouterMetrics,
    ExecutionQualityReport,
    # Factory functions (legacy)
    get_smart_router,
    reset_smart_router,
)

# ============================================================================
# EXPORTS
# ============================================================================
__all__ = [
    # ========== Orderbook Analyzer ==========
    "OrderbookAnalyzer",
    "OrderBookConfig",
    "LiquidityLevel",
    "OrderBookState",
    "SpreadCategory",
    "PriceLevel",
    "DepthAnalysis",
    "MarketImpactEstimate",
    "LiquidityReport",
    "OptimalLimitPrice",
    "get_orderbook_analyzer",
    "reset_orderbook_analyzer",

    # ========== Execution Optimizer ==========
    "ExecutionOptimizer",
    "ExecutionOptimizerConfig",
    "FeeStructure",
    "ExecutionUrgency",
    "OptimalOrderType",
    "TimingStrategy",
    "CostComponent",
    "CostBreakdown",
    "OptimizationResult",
    "ExecutionMetrics",
    "get_execution_optimizer",
    "reset_execution_optimizer",

    # ========== Smart Order Router V2 ==========
    "SmartOrderRouterV2",
    "SmartRouterConfigV2",
    "RoutingStrategy",
    "ExecutionMode",
    "OrderStatus",
    "RoutingDecision",
    "ExecutionResult",
    "RouterMetricsV2",
    "get_smart_order_router",
    "reset_smart_order_router",

    # ========== TWAP/VWAP Algorithms ==========
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "TWAPConfig",
    "VWAPConfig",
    "ExecutionState",
    "AdaptiveMode",
    "BenchmarkType",
    "ChunkSchedule",
    "ExecutionBenchmark",
    "SlippageAlert",
    "AlgorithmMetrics",
    "SlippageTracker",
    "MarketImpactEstimator",
    "AlgorithmMetricsAggregator",
    "create_twap_algorithm",
    "create_vwap_algorithm",
    "get_twap_algorithm",
    "get_vwap_algorithm",
    "reset_algorithms",

    # ========== Execution Scheduler (Phase 4.2) ==========
    "ExecutionScheduler",
    "OrderPriority",
    "AlgorithmType",
    "SchedulerState",
    "OrderLifecycleState",
    "ScheduledOrder",
    "ChunkExecution",
    "ExecutionReport",
    "SchedulerMetrics",
    "get_execution_scheduler",
    "reset_execution_scheduler",

    # ========== Legacy Smart Router (backward compat) ==========
    "SmartOrderRouter",
    "SmartRouterConfig",
    "LegacyExecutionUrgency",
    "ExecutionStrategyType",
    "OrderTypeSelection",
    "OrderBookLevel",
    "OrderBookAnalysis",
    "SlippageEstimate",
    "OrderTypeRecommendation",
    "ExecutionRecord",
    "RouterMetrics",
    "ExecutionQualityReport",
    "get_smart_router",
    "reset_smart_router",
]
