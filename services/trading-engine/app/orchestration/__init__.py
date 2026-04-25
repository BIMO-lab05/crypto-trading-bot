"""
Multi-Strategy Orchestration Engine
====================================
Phase 9: Sophisticated system for managing multiple trading strategies simultaneously

This module provides comprehensive strategy orchestration capabilities:

1. StrategyOrchestrator - Central coordinator for multi-strategy management
   - Strategy lifecycle management (register, activate, pause, deactivate)
   - Signal routing and conflict resolution
   - Capital allocation across strategies
   - Performance tracking and auto-pause logic
   - Integration with execution systems

2. StrategyRegistry - Central registry for strategy definitions
   - Strategy registration and versioning
   - Metadata management
   - Strategy discovery by type, symbol, timeframe
   - Configuration validation

3. AllocationManager - Dynamic capital allocation
   - Multiple allocation methods (equal, risk parity, Kelly, performance-based)
   - Automatic rebalancing
   - Risk budget management
   - Correlation-aware adjustments

4. ConflictResolver - Handle opposing signals from different strategies
   - Weighted voting system
   - Priority-based resolution
   - Strongest signal selection
   - Unanimous/majority/veto modes
   - Signal aggregation

5. StrategyMetrics - Per-strategy performance tracking
   - Comprehensive metrics (Sharpe, Sortino, Calmar, etc.)
   - Comparative analytics across strategies
   - Correlation analysis
   - Auto-pause detection for underperformers
   - Attribution analysis

6. SignalAggregator - Signal collection and conflict detection
   - Collect signals from all active strategies
   - Group signals by symbol
   - Detect and analyze conflicts
   - Prioritize signals for resolution

7. PerformanceTracker - Enhanced performance tracking with reallocation triggers
   - Underperformer detection with recommendations
   - Reallocation trigger detection
   - Attribution analysis
   - Comparative rankings

8. RiskCoordinator - Global risk management
   - Portfolio-wide risk limits
   - Per-strategy risk budgets
   - Correlation limits
   - Emergency stop coordination

Integration Points:
- DynamicBudgetManager: Risk budgeting and limits
- KellyPositionSizer: Optimal position sizing
- SmartOrderRouter: Intelligent execution
- Analytics Service: Metrics publishing

Example Usage:
    from app.orchestration import (
        StrategyOrchestrator,
        OrchestratorConfig,
        get_strategy_orchestrator,
        StrategySignal,
        SignalDirection,
    )

    # Initialize orchestrator
    config = OrchestratorConfig(
        total_capital=100000,
        allocation_method=AllocationMethod.PERFORMANCE_BASED,
        default_conflict_resolution=ConflictResolutionMethod.WEIGHTED_VOTING
    )
    orchestrator = get_strategy_orchestrator(config)

    # Register strategies
    orchestrator.register_strategy(
        strategy_id="trend_following_v1",
        name="Trend Following Strategy",
        strategy_type="trend_following",
        symbols=["BTCUSDT", "ETHUSDT"],
        allocation_pct=20.0,
        auto_activate=True
    )

    orchestrator.register_strategy(
        strategy_id="mean_reversion_v1",
        name="Mean Reversion Strategy",
        strategy_type="mean_reversion",
        symbols=["BTCUSDT"],
        allocation_pct=15.0,
        auto_activate=True
    )

    # Submit signals from strategies
    signal = StrategySignal(
        signal_id="sig_001",
        strategy_id="trend_following_v1",
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        direction=SignalDirection.LONG,
        action="BUY",
        strength=0.75,
        confidence=0.8,
        stop_loss_pct=2.0,
        take_profit_pct=4.0
    )
    orchestrator.submit_signal(signal)

    # Get aggregated signal after conflict resolution
    aggregated = orchestrator.get_aggregated_signal("BTCUSDT")
    if aggregated and aggregated.direction != SignalDirection.FLAT:
        # Execute trade using aggregated signal
        pass

    # Record completed trade
    from app.orchestration.metrics import MetricsTrade
    trade = MetricsTrade(
        trade_id="trade_001",
        strategy_id="trend_following_v1",
        symbol="BTCUSDT",
        side="LONG",
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=50000.0,
        exit_price=51000.0,
        quantity=0.1,
        pnl=100.0,
        pnl_pct=2.0
    )
    orchestrator.record_trade(trade)

    # Get status
    status = orchestrator.get_orchestrator_status()
    strategy_status = orchestrator.get_strategy_status("trend_following_v1")

    # Compare strategies
    comparison = orchestrator.compare_strategies()
    correlations = orchestrator.get_correlations()

Author: Backend Developer Agent
Date: 2025-12-11
Phase: 9 - Multi-Strategy Orchestration Engine
"""

# =============================================================================
# MODELS - Data structures for orchestration
# =============================================================================

from app.orchestration.models import (
    # Enumerations
    StrategyStatus,
    StrategyType,
    RiskProfile,
    Timeframe,
    SignalDirection,
    ConflictResolutionMethod,
    AllocationMethod,
    RebalanceTrigger,

    # Strategy Configuration
    StrategyMetadata,
    StrategyConfig,
    StrategyState,

    # Signals
    StrategySignal,
    AggregatedSignal,

    # Allocation
    StrategyAllocation,
    AllocationSnapshot,

    # Performance
    StrategyPerformanceMetrics,

    # Orchestrator Config
    OrchestratorConfig,

    # API Models
    RegisterStrategyRequest,
    UpdateStrategyStatusRequest,
    UpdateAllocationRequest,
    SubmitSignalRequest,
    OrchestratorStatusResponse,
    StrategyStatusResponse,
    SignalAggregationResponse,
)

# =============================================================================
# REGISTRY - Strategy registration and discovery
# =============================================================================

from app.orchestration.registry import (
    StrategyRegistry,
    StrategyVersion,
    StrategyFactory,
    get_strategy_registry,
    reset_strategy_registry,
)

# =============================================================================
# ALLOCATION - Capital allocation management
# =============================================================================

from app.orchestration.allocation import (
    AllocationManager,
    AllocationConfig,
    get_allocation_manager,
    reset_allocation_manager,
)

# =============================================================================
# CONFLICT RESOLUTION - Signal conflict handling
# =============================================================================

from app.orchestration.conflict_resolver import (
    ConflictResolver,
    ConflictResolverConfig,
    get_conflict_resolver,
    reset_conflict_resolver,
)

# =============================================================================
# METRICS - Performance tracking
# =============================================================================

from app.orchestration.metrics import (
    StrategyMetrics,
    StrategyMetricsConfig,
    MetricsTrade,
    get_strategy_metrics_tracker,
    reset_strategy_metrics_tracker,
)

# =============================================================================
# ORCHESTRATOR - Main coordination engine
# =============================================================================

from app.orchestration.orchestrator import (
    StrategyOrchestrator,
    OrchestratorEvent,
    get_strategy_orchestrator,
    reset_strategy_orchestrator,
)

# =============================================================================
# SIGNAL AGGREGATOR - Signal collection and conflict detection
# =============================================================================

from app.orchestration.signal_aggregator import (
    SignalAggregator,
    SignalAggregatorConfig,
    SignalMetadata,
    ConflictDetectionResult,
    get_signal_aggregator,
    reset_signal_aggregator,
)

# =============================================================================
# PERFORMANCE TRACKER - Enhanced tracking with reallocation triggers
# =============================================================================

from app.orchestration.performance_tracker import (
    PerformanceTracker,
    PerformanceTrackerConfig,
    ReallocationRecommendation,
    UnderperformerRecord,
    get_performance_tracker,
    reset_performance_tracker,
)

# =============================================================================
# RISK COORDINATOR - Global risk management
# =============================================================================

from app.orchestration.risk_coordinator import (
    RiskCoordinator,
    RiskCoordinatorConfig,
    RiskUtilization,
    RiskCheckResult,
    get_risk_coordinator,
    reset_risk_coordinator,
)

# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # === Models ===
    # Enums
    "StrategyStatus",
    "StrategyType",
    "RiskProfile",
    "Timeframe",
    "SignalDirection",
    "ConflictResolutionMethod",
    "AllocationMethod",
    "RebalanceTrigger",
    # Strategy Configuration
    "StrategyMetadata",
    "StrategyConfig",
    "StrategyState",
    # Signals
    "StrategySignal",
    "AggregatedSignal",
    # Allocation
    "StrategyAllocation",
    "AllocationSnapshot",
    # Performance
    "StrategyPerformanceMetrics",
    # Config
    "OrchestratorConfig",
    # API Models
    "RegisterStrategyRequest",
    "UpdateStrategyStatusRequest",
    "UpdateAllocationRequest",
    "SubmitSignalRequest",
    "OrchestratorStatusResponse",
    "StrategyStatusResponse",
    "SignalAggregationResponse",

    # === Registry ===
    "StrategyRegistry",
    "StrategyVersion",
    "StrategyFactory",
    "get_strategy_registry",
    "reset_strategy_registry",

    # === Allocation ===
    "AllocationManager",
    "AllocationConfig",
    "get_allocation_manager",
    "reset_allocation_manager",

    # === Conflict Resolution ===
    "ConflictResolver",
    "ConflictResolverConfig",
    "get_conflict_resolver",
    "reset_conflict_resolver",

    # === Metrics ===
    "StrategyMetrics",
    "StrategyMetricsConfig",
    "MetricsTrade",
    "get_strategy_metrics_tracker",
    "reset_strategy_metrics_tracker",

    # === Orchestrator ===
    "StrategyOrchestrator",
    "OrchestratorEvent",
    "get_strategy_orchestrator",
    "reset_strategy_orchestrator",

    # === Signal Aggregator ===
    "SignalAggregator",
    "SignalAggregatorConfig",
    "SignalMetadata",
    "ConflictDetectionResult",
    "get_signal_aggregator",
    "reset_signal_aggregator",

    # === Performance Tracker ===
    "PerformanceTracker",
    "PerformanceTrackerConfig",
    "ReallocationRecommendation",
    "UnderperformerRecord",
    "get_performance_tracker",
    "reset_performance_tracker",

    # === Risk Coordinator ===
    "RiskCoordinator",
    "RiskCoordinatorConfig",
    "RiskUtilization",
    "RiskCheckResult",
    "get_risk_coordinator",
    "reset_risk_coordinator",
]

# Module version
__version__ = "1.1.0"
