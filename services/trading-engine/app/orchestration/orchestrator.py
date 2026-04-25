"""
Strategy Orchestrator
======================
Purpose: Central coordinator for managing multiple trading strategies simultaneously

The Strategy Orchestrator is the main integration component that:
1. Manages multiple strategy instances
2. Coordinates capital allocation across strategies
3. Handles strategy activation/deactivation
4. Routes signals through conflict resolution
5. Tracks performance per strategy
6. Integrates with execution systems

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
import uuid

from app.orchestration.models import (
    StrategyMetadata,
    StrategyConfig,
    StrategyState,
    StrategyStatus,
    StrategySignal,
    AggregatedSignal,
    SignalDirection,
    OrchestratorConfig,
    AllocationMethod,
    ConflictResolutionMethod,
    RegisterStrategyRequest,
    UpdateStrategyStatusRequest,
    OrchestratorStatusResponse,
    StrategyStatusResponse,
)
from app.orchestration.registry import (
    StrategyRegistry,
    get_strategy_registry,
)
from app.orchestration.allocation import (
    AllocationManager,
    AllocationConfig,
    get_allocation_manager,
)
from app.orchestration.conflict_resolver import (
    ConflictResolver,
    ConflictResolverConfig,
    get_conflict_resolver,
)
from app.orchestration.metrics import (
    StrategyMetrics,
    StrategyMetricsConfig,
    MetricsTrade,
    get_strategy_metrics_tracker,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ORCHESTRATOR EVENTS
# =============================================================================

@dataclass
class OrchestratorEvent:
    """Event emitted by orchestrator for external consumption"""
    event_type: str
    timestamp: datetime
    data: Dict[str, Any]
    strategy_id: Optional[str] = None
    symbol: Optional[str] = None


# =============================================================================
# STRATEGY ORCHESTRATOR
# =============================================================================

class StrategyOrchestrator:
    """
    Multi-Strategy Orchestration Engine

    The central coordinator for managing multiple trading strategies simultaneously.
    Provides a unified interface for strategy management, signal processing,
    capital allocation, and performance tracking.

    Key Responsibilities:

    1. Strategy Lifecycle Management:
       - Register/unregister strategies
       - Activate/deactivate/pause strategies
       - Handle warmup periods
       - Manage cooldown after losses

    2. Capital Allocation:
       - Distribute capital across active strategies
       - Dynamic rebalancing based on performance
       - Risk budget management
       - Correlation-aware allocation

    3. Signal Processing:
       - Receive signals from multiple strategies
       - Detect and resolve conflicts
       - Aggregate signals for execution
       - Priority-based signal routing

    4. Performance Tracking:
       - Per-strategy metrics
       - Comparative analytics
       - Auto-pause underperformers
       - Attribution analysis

    5. Execution Integration:
       - Interface with SmartOrderRouter
       - Position sizing via KellyPositionSizer
       - Risk budgeting via DynamicBudgetManager
       - Order execution callbacks

    Architecture:
    ```
    ┌─────────────────────────────────────────────────────────────┐
    │                   Strategy Orchestrator                      │
    ├─────────────────────────────────────────────────────────────┤
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
    │  │  Registry   │  │  Allocator  │  │  ConflictResolver   │  │
    │  │  (metadata) │  │  (capital)  │  │     (signals)       │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────┘  │
    │                                                              │
    │  ┌─────────────┐  ┌─────────────────────────────────────┐   │
    │  │   Metrics   │  │         Strategy Instances          │   │
    │  │  (tracking) │  │  [trend] [arb] [grid] [momentum]    │   │
    │  └─────────────┘  └─────────────────────────────────────┘   │
    ├─────────────────────────────────────────────────────────────┤
    │                    External Integrations                     │
    │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐    │
    │  │ SmartRouter│  │   Kelly    │  │   DynamicBudget    │    │
    │  │ (execution)│  │  (sizing)  │  │    (risk mgmt)     │    │
    │  └────────────┘  └────────────┘  └────────────────────┘    │
    └─────────────────────────────────────────────────────────────┘
    ```

    Usage:
        # Initialize orchestrator
        config = OrchestratorConfig(total_capital=100000)
        orchestrator = StrategyOrchestrator(config)

        # Register strategies
        orchestrator.register_strategy(
            strategy_id="trend_following",
            name="Trend Following Strategy",
            strategy_type="trend_following",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=20.0
        )

        # Activate strategy
        orchestrator.activate_strategy("trend_following")

        # Process signals
        signal = StrategySignal(...)
        orchestrator.submit_signal(signal)

        # Get aggregated signal for execution
        aggregated = orchestrator.get_aggregated_signal("BTCUSDT")

        # Record trade completion
        orchestrator.record_trade(trade)

        # Check strategy health
        status = orchestrator.get_strategy_status("trend_following")
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        """
        Initialize the Strategy Orchestrator

        Args:
            config: Orchestrator configuration
        """
        self.config = config or OrchestratorConfig()
        self._lock = RLock()

        # Initialize sub-components
        self._registry = get_strategy_registry()
        self._allocator = get_allocation_manager(
            AllocationConfig(
                total_capital=self.config.total_capital,
                allocation_method=self.config.allocation_method,
                max_total_exposure_pct=self.config.max_total_exposure_pct,
                cash_reserve_pct=self.config.cash_reserve_pct,
            )
        )
        self._conflict_resolver = get_conflict_resolver(
            ConflictResolverConfig(
                default_method=self.config.default_conflict_resolution,
                min_agreement_ratio=self.config.min_agreement_ratio,
            )
        )
        self._metrics = get_strategy_metrics_tracker()

        # Strategy state tracking
        self._strategy_states: Dict[str, StrategyState] = {}

        # Active strategy instances
        self._strategy_instances: Dict[str, Any] = {}

        # Event callbacks
        self._event_callbacks: List[Callable[[OrchestratorEvent], None]] = []

        # Portfolio-level tracking
        self._is_active: bool = True
        self._total_pnl: float = 0.0
        self._today_pnl: float = 0.0
        self._peak_equity: float = self.config.total_capital
        self._current_drawdown_pct: float = 0.0
        self._last_metrics_update: Optional[datetime] = None

        # Daily reset tracking
        self._current_day: Optional[datetime] = None

        # Background tasks
        self._background_tasks: List[asyncio.Task] = []

        logger.info(
            f"StrategyOrchestrator initialized: "
            f"capital=${self.config.total_capital:,.0f}, "
            f"allocation={self.config.allocation_method.value}, "
            f"conflict_resolution={self.config.default_conflict_resolution.value}"
        )

    # =========================================================================
    # STRATEGY REGISTRATION
    # =========================================================================

    def register_strategy(
        self,
        strategy_id: str,
        name: str,
        strategy_type: str = "trend_following",
        risk_profile: str = "moderate",
        symbols: Optional[List[str]] = None,
        timeframe: str = "1h",
        allocation_pct: float = 10.0,
        priority: int = 50,
        description: str = "",
        auto_activate: bool = False
    ) -> Dict[str, Any]:
        """
        Register a new strategy with the orchestrator

        Args:
            strategy_id: Unique strategy identifier
            name: Human-readable strategy name
            strategy_type: Type classification (trend_following, mean_reversion, etc.)
            risk_profile: Risk profile (conservative, moderate, aggressive)
            symbols: List of symbols the strategy trades
            timeframe: Primary trading timeframe
            allocation_pct: Target capital allocation percentage
            priority: Priority for conflict resolution (1-100)
            description: Strategy description
            auto_activate: Whether to automatically activate after registration

        Returns:
            Registration result dictionary
        """
        with self._lock:
            # Create registration request
            request = RegisterStrategyRequest(
                strategy_id=strategy_id,
                name=name,
                strategy_type=strategy_type,
                risk_profile=risk_profile,
                supported_symbols=symbols or [],
                primary_timeframe=timeframe,
                target_allocation_pct=allocation_pct,
                priority=priority,
                description=description
            )

            # Register in registry
            registry_result = self._registry.register_from_request(request)

            if not registry_result.get("success"):
                return registry_result

            # Get config from registry
            config = self._registry.get_config(strategy_id)

            # Initialize state
            self._strategy_states[strategy_id] = StrategyState(
                strategy_id=strategy_id,
                status=StrategyStatus.DISABLED,
                status_reason="Newly registered"
            )

            # Add to allocator
            self._allocator.add_strategy(
                strategy_id=strategy_id,
                config=config,
                target_pct=allocation_pct
            )

            # Register with conflict resolver
            self._conflict_resolver.register_strategy(
                strategy_id=strategy_id,
                config=config,
                state=self._strategy_states[strategy_id]
            )

            # Auto-activate if requested
            if auto_activate:
                self.activate_strategy(strategy_id)

            # Emit event
            self._emit_event(
                "strategy_registered",
                strategy_id=strategy_id,
                data={
                    "name": name,
                    "type": strategy_type,
                    "allocation_pct": allocation_pct,
                    "auto_activated": auto_activate
                }
            )

            logger.info(
                f"Registered strategy: {strategy_id} ({name}), "
                f"type={strategy_type}, allocation={allocation_pct}%"
            )

            return {
                "success": True,
                "strategy_id": strategy_id,
                "version": registry_result.get("version"),
                "status": StrategyStatus.ACTIVE.value if auto_activate else StrategyStatus.DISABLED.value
            }

    def unregister_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Unregister a strategy from the orchestrator

        Args:
            strategy_id: Strategy to unregister

        Returns:
            Unregistration result
        """
        with self._lock:
            # Check if strategy exists
            if strategy_id not in self._strategy_states:
                return {"success": False, "error": "Strategy not found"}

            # Deactivate first
            if self._strategy_states[strategy_id].status == StrategyStatus.ACTIVE:
                self.deactivate_strategy(strategy_id)

            # Remove from all components
            self._registry.unregister_strategy(strategy_id)
            self._allocator.remove_strategy(strategy_id)
            del self._strategy_states[strategy_id]
            self._strategy_instances.pop(strategy_id, None)

            # Emit event
            self._emit_event(
                "strategy_unregistered",
                strategy_id=strategy_id,
                data={}
            )

            logger.info(f"Unregistered strategy: {strategy_id}")

            return {"success": True, "strategy_id": strategy_id}

    # =========================================================================
    # STRATEGY LIFECYCLE
    # =========================================================================

    def activate_strategy(
        self,
        strategy_id: str,
        warmup_minutes: int = 0
    ) -> Dict[str, Any]:
        """
        Activate a strategy for trading

        Args:
            strategy_id: Strategy to activate
            warmup_minutes: Optional warmup period before trading

        Returns:
            Activation result
        """
        with self._lock:
            if strategy_id not in self._strategy_states:
                return {"success": False, "error": "Strategy not found"}

            state = self._strategy_states[strategy_id]

            # Check if already active
            if state.status == StrategyStatus.ACTIVE:
                return {"success": True, "message": "Already active"}

            # Check if in cooldown
            if state.is_in_cooldown:
                return {
                    "success": False,
                    "error": f"In cooldown until {state.cooldown_until.isoformat()}"
                }

            # Handle warmup
            if warmup_minutes > 0:
                state.status = StrategyStatus.WARMING_UP
                state.warming_up_until = datetime.now(timezone.utc) + timedelta(minutes=warmup_minutes)
                state.status_reason = f"Warming up for {warmup_minutes} minutes"
            else:
                state.status = StrategyStatus.ACTIVE
                state.status_reason = "Activated"

            state.status_changed_at = datetime.now(timezone.utc)

            # Update allocator and conflict resolver
            self._allocator.update_strategy_state(strategy_id, state)
            self._conflict_resolver.update_strategy_data(strategy_id, state=state)

            # Recalculate allocations
            self._allocator.calculate_allocations()

            # Emit event
            self._emit_event(
                "strategy_activated",
                strategy_id=strategy_id,
                data={
                    "status": state.status.value,
                    "warmup_until": state.warming_up_until.isoformat() if state.warming_up_until else None
                }
            )

            logger.info(f"Activated strategy: {strategy_id} (status={state.status.value})")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "status": state.status.value
            }

    def deactivate_strategy(
        self,
        strategy_id: str,
        reason: str = "Manual deactivation"
    ) -> Dict[str, Any]:
        """
        Deactivate a strategy (stop trading)

        Args:
            strategy_id: Strategy to deactivate
            reason: Reason for deactivation

        Returns:
            Deactivation result
        """
        with self._lock:
            if strategy_id not in self._strategy_states:
                return {"success": False, "error": "Strategy not found"}

            state = self._strategy_states[strategy_id]
            state.status = StrategyStatus.DISABLED
            state.status_reason = reason
            state.status_changed_at = datetime.now(timezone.utc)

            # Update components
            self._allocator.update_strategy_state(strategy_id, state)
            self._conflict_resolver.update_strategy_data(strategy_id, state=state)

            # Clear pending signals
            # Note: This will be per-symbol, handled by caller

            # Emit event
            self._emit_event(
                "strategy_deactivated",
                strategy_id=strategy_id,
                data={"reason": reason}
            )

            logger.info(f"Deactivated strategy: {strategy_id} ({reason})")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "reason": reason
            }

    def pause_strategy(
        self,
        strategy_id: str,
        reason: str = "Manual pause",
        cooldown_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Pause a strategy temporarily

        Args:
            strategy_id: Strategy to pause
            reason: Reason for pause
            cooldown_hours: Optional cooldown period

        Returns:
            Pause result
        """
        with self._lock:
            if strategy_id not in self._strategy_states:
                return {"success": False, "error": "Strategy not found"}

            state = self._strategy_states[strategy_id]

            if cooldown_hours:
                state.status = StrategyStatus.COOLDOWN
                state.cooldown_until = datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)
            else:
                state.status = StrategyStatus.PAUSED

            state.status_reason = reason
            state.status_changed_at = datetime.now(timezone.utc)

            # Update components
            self._allocator.update_strategy_state(strategy_id, state)
            self._conflict_resolver.update_strategy_data(strategy_id, state=state)

            # Emit event
            self._emit_event(
                "strategy_paused",
                strategy_id=strategy_id,
                data={
                    "reason": reason,
                    "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None
                }
            )

            logger.info(f"Paused strategy: {strategy_id} ({reason})")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "status": state.status.value,
                "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None
            }

    def update_strategy_status(
        self,
        strategy_id: str,
        status: str,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Update strategy status

        Args:
            strategy_id: Strategy identifier
            status: New status string
            reason: Reason for change

        Returns:
            Update result
        """
        try:
            new_status = StrategyStatus(status)
        except ValueError:
            return {"success": False, "error": f"Invalid status: {status}"}

        if new_status == StrategyStatus.ACTIVE:
            return self.activate_strategy(strategy_id)
        elif new_status == StrategyStatus.DISABLED:
            return self.deactivate_strategy(strategy_id, reason)
        elif new_status == StrategyStatus.PAUSED:
            return self.pause_strategy(strategy_id, reason)
        else:
            with self._lock:
                if strategy_id not in self._strategy_states:
                    return {"success": False, "error": "Strategy not found"}

                state = self._strategy_states[strategy_id]
                state.status = new_status
                state.status_reason = reason
                state.status_changed_at = datetime.now(timezone.utc)

                return {"success": True, "status": new_status.value}

    # =========================================================================
    # SIGNAL PROCESSING
    # =========================================================================

    def submit_signal(self, signal: StrategySignal) -> Dict[str, Any]:
        """
        Submit a signal from a strategy

        Args:
            signal: Strategy signal to submit

        Returns:
            Submission result
        """
        with self._lock:
            strategy_id = signal.strategy_id

            # Validate strategy
            if strategy_id not in self._strategy_states:
                return {
                    "accepted": False,
                    "reason": f"Unknown strategy: {strategy_id}"
                }

            # Check strategy status
            state = self._strategy_states[strategy_id]
            if state.status != StrategyStatus.ACTIVE:
                # Check if warmup completed
                if state.status == StrategyStatus.WARMING_UP and not state.is_warming_up:
                    state.status = StrategyStatus.ACTIVE
                    state.status_reason = "Warmup completed"
                else:
                    return {
                        "accepted": False,
                        "reason": f"Strategy not active (status={state.status.value})"
                    }

            # Check if cooldown ended
            if state.status == StrategyStatus.COOLDOWN and not state.is_in_cooldown:
                state.status = StrategyStatus.ACTIVE
                state.status_reason = "Cooldown completed"

            # Update last signal time
            state.last_signal_at = datetime.now(timezone.utc)

            # Submit to conflict resolver
            result = self._conflict_resolver.submit_signal(signal)

            if result["accepted"]:
                logger.debug(
                    f"Signal accepted: {strategy_id} -> {signal.symbol} "
                    f"{signal.direction.value} (conf={signal.confidence:.2f})"
                )

            return result

    def submit_signals(self, signals: List[StrategySignal]) -> Dict[str, Any]:
        """Submit multiple signals at once"""
        results = []
        for signal in signals:
            result = self.submit_signal(signal)
            results.append({
                "signal_id": signal.signal_id,
                "strategy_id": signal.strategy_id,
                "symbol": signal.symbol,
                **result
            })

        accepted = sum(1 for r in results if r.get("accepted"))

        return {
            "total": len(signals),
            "accepted": accepted,
            "rejected": len(signals) - accepted,
            "results": results
        }

    def get_aggregated_signal(
        self,
        symbol: str,
        resolution_method: Optional[ConflictResolutionMethod] = None
    ) -> Optional[AggregatedSignal]:
        """
        Get aggregated signal for a symbol after conflict resolution

        Args:
            symbol: Trading symbol
            resolution_method: Override resolution method

        Returns:
            AggregatedSignal or None
        """
        with self._lock:
            # Detect conflicts first
            conflict_analysis = self._conflict_resolver.detect_conflicts(symbol)

            # Resolve and get aggregated signal
            aggregated = self._conflict_resolver.resolve_conflicts(symbol, resolution_method)

            if aggregated:
                # Apply position sizing based on signal quality
                if aggregated.signal_quality_score > 0.7:
                    size_multiplier = 1.2
                elif aggregated.signal_quality_score > 0.5:
                    size_multiplier = 1.0
                else:
                    size_multiplier = 0.7

                aggregated.suggested_position_size_pct *= size_multiplier

            return aggregated

    def get_all_pending_signals(self) -> Dict[str, List[StrategySignal]]:
        """Get all pending signals grouped by symbol"""
        with self._lock:
            result = {}
            for symbol in self._conflict_resolver.get_all_pending_symbols():
                result[symbol] = self._conflict_resolver.get_pending_signals(symbol)
            return result

    def clear_signals(self, symbol: Optional[str] = None) -> None:
        """Clear pending signals"""
        with self._lock:
            if symbol:
                self._conflict_resolver.clear_symbol(symbol)
            else:
                self._conflict_resolver.clear_all()

    # =========================================================================
    # TRADE RECORDING
    # =========================================================================

    def record_trade(self, trade: MetricsTrade) -> Dict[str, Any]:
        """
        Record a completed trade for metrics

        Args:
            trade: Completed trade record

        Returns:
            Recording result with updated metrics
        """
        with self._lock:
            strategy_id = trade.strategy_id

            if strategy_id not in self._strategy_states:
                return {"success": False, "error": "Unknown strategy"}

            state = self._strategy_states[strategy_id]

            # Update state
            state.total_trades += 1
            state.last_trade_at = datetime.now(timezone.utc)

            if trade.is_winner:
                state.winning_trades += 1
                if state.consecutive_losses > 0:
                    state.consecutive_losses = 0
                state.consecutive_wins += 1
            else:
                state.losing_trades += 1
                if state.consecutive_wins > 0:
                    state.consecutive_wins = 0
                state.consecutive_losses += 1

            state.total_pnl += trade.pnl
            state.today_pnl += trade.pnl

            # Update peak and drawdown
            if state.total_pnl > state.peak_equity:
                state.peak_equity = state.total_pnl

            if state.peak_equity > 0:
                state.current_drawdown_pct = max(
                    0,
                    (state.peak_equity - state.total_pnl) / state.peak_equity * 100
                )
                if state.current_drawdown_pct > state.max_drawdown_pct:
                    state.max_drawdown_pct = state.current_drawdown_pct

            # Record in metrics tracker
            result = self._metrics.record_trade(trade)

            # Update portfolio-level PnL
            self._total_pnl += trade.pnl
            self._today_pnl += trade.pnl

            # Update portfolio drawdown
            current_equity = self.config.total_capital + self._total_pnl
            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
            if self._peak_equity > 0:
                self._current_drawdown_pct = max(
                    0,
                    (self._peak_equity - current_equity) / self._peak_equity * 100
                )

            # Update allocator with used capital
            allocation = self._allocator.get_allocation(strategy_id)
            if allocation:
                self._allocator.update_used_capital(
                    strategy_id,
                    allocation.used_capital + (trade.pnl if trade.pnl > 0 else 0)
                )

            # Check for auto-pause
            should_pause, pause_reason = self._check_auto_pause(strategy_id, state)
            if should_pause:
                self.pause_strategy(strategy_id, pause_reason, cooldown_hours=24)

            # Emit event
            self._emit_event(
                "trade_recorded",
                strategy_id=strategy_id,
                symbol=trade.symbol,
                data={
                    "trade_id": trade.trade_id,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "is_winner": trade.is_winner,
                    "strategy_total_pnl": state.total_pnl,
                    "portfolio_total_pnl": self._total_pnl
                }
            )

            logger.info(
                f"Recorded trade for {strategy_id}: "
                f"{'WIN' if trade.is_winner else 'LOSS'} ${trade.pnl:+.2f} "
                f"(strategy PnL: ${state.total_pnl:.2f})"
            )

            return {
                "success": True,
                **result,
                "strategy_state": state.to_dict()
            }

    def _check_auto_pause(
        self,
        strategy_id: str,
        state: StrategyState
    ) -> Tuple[bool, Optional[str]]:
        """Check if strategy should be auto-paused"""
        if not self.config.auto_pause_on_drawdown:
            return False, None

        # Check drawdown
        if state.current_drawdown_pct >= self.config.max_total_drawdown_pct:
            return True, f"Drawdown {state.current_drawdown_pct:.1f}% exceeds limit"

        # Check consecutive losses
        config = self._registry.get_config(strategy_id)
        if config and state.consecutive_losses >= config.max_consecutive_losses:
            return True, f"Consecutive losses ({state.consecutive_losses}) exceed limit"

        # Delegate to metrics tracker
        should_pause, reason = self._metrics.should_auto_pause(strategy_id)
        return should_pause, reason

    # =========================================================================
    # ALLOCATION MANAGEMENT
    # =========================================================================

    def update_allocation(
        self,
        strategy_id: str,
        target_pct: Optional[float] = None,
        min_pct: Optional[float] = None,
        max_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update strategy allocation

        Args:
            strategy_id: Strategy identifier
            target_pct: New target allocation percentage
            min_pct: New minimum allocation
            max_pct: New maximum allocation

        Returns:
            Update result
        """
        with self._lock:
            allocation = self._allocator.get_allocation(strategy_id)
            if not allocation:
                return {"success": False, "error": "Strategy not found"}

            if target_pct is not None:
                allocation.target_pct = target_pct
            if min_pct is not None:
                allocation.min_pct = min_pct
            if max_pct is not None:
                allocation.max_pct = max_pct

            # Recalculate all allocations
            self._allocator.calculate_allocations()

            return {
                "success": True,
                "strategy_id": strategy_id,
                "new_allocation": {
                    "target_pct": allocation.target_pct,
                    "min_pct": allocation.min_pct,
                    "max_pct": allocation.max_pct,
                    "allocated_capital": allocation.allocated_capital
                }
            }

    def get_available_capital(self, strategy_id: str) -> float:
        """Get available capital for a strategy"""
        return self._allocator.get_available_capital(strategy_id)

    def trigger_rebalance(self) -> Dict[str, Any]:
        """Manually trigger portfolio rebalancing"""
        with self._lock:
            if self._allocator.needs_rebalancing():
                result = self._allocator.execute_rebalance()

                # Emit event
                self._emit_event(
                    "portfolio_rebalanced",
                    data=result
                )

                return result
            else:
                return {
                    "success": True,
                    "message": "No rebalancing needed"
                }

    # =========================================================================
    # STATUS AND METRICS
    # =========================================================================

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get overall orchestrator status"""
        with self._lock:
            # Count strategies by status
            status_counts = {}
            for state in self._strategy_states.values():
                status = state.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            # Get allocation summary
            allocation_snapshot = self._allocator.get_snapshot()

            return {
                "is_active": self._is_active,
                "total_capital": self.config.total_capital,
                "total_allocated_pct": allocation_snapshot.total_allocated_pct,
                "total_used_pct": allocation_snapshot.total_used_pct,
                "cash_reserve_pct": allocation_snapshot.cash_reserve_pct,
                "strategy_counts": status_counts,
                "active_strategies": status_counts.get("active", 0),
                "total_strategies": len(self._strategy_states),
                "total_open_positions": sum(s.open_positions for s in self._strategy_states.values()),
                "today_pnl": self._today_pnl,
                "total_pnl": self._total_pnl,
                "current_drawdown_pct": self._current_drawdown_pct,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    def get_strategy_status(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get status for a single strategy"""
        with self._lock:
            if strategy_id not in self._strategy_states:
                return None

            state = self._strategy_states[strategy_id]
            metadata = self._registry.get_strategy(strategy_id)
            allocation = self._allocator.get_allocation(strategy_id)

            return {
                "strategy_id": strategy_id,
                "name": metadata.name if metadata else strategy_id,
                "status": state.status.value,
                "status_reason": state.status_reason,
                "current_allocation_pct": allocation.current_pct if allocation else 0,
                "total_trades": state.total_trades,
                "win_rate": state.win_rate,
                "total_pnl": state.total_pnl,
                "today_pnl": state.today_pnl,
                "current_drawdown_pct": state.current_drawdown_pct,
                "max_drawdown_pct": state.max_drawdown_pct,
                "consecutive_losses": state.consecutive_losses,
                "open_positions": state.open_positions,
                "last_trade_at": state.last_trade_at.isoformat() if state.last_trade_at else None,
                "last_signal_at": state.last_signal_at.isoformat() if state.last_signal_at else None,
            }

    def get_all_strategies_status(self) -> List[Dict[str, Any]]:
        """Get status for all strategies"""
        with self._lock:
            return [
                self.get_strategy_status(sid)
                for sid in self._strategy_states.keys()
            ]

    def get_strategy_metrics(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed metrics for a strategy"""
        metrics = self._metrics.get_strategy_metrics(strategy_id)
        if metrics:
            return metrics.to_dict()
        return None

    def compare_strategies(self) -> Dict[str, Any]:
        """Compare all strategy performance"""
        return self._metrics.compare_strategies()

    def get_correlations(self) -> Dict[str, Dict[str, float]]:
        """Get strategy return correlations"""
        return self._metrics.get_correlations()

    def get_portfolio_attribution(self) -> Dict[str, Any]:
        """Get portfolio return attribution by strategy"""
        return self._metrics.get_portfolio_attribution()

    # =========================================================================
    # PORTFOLIO MANAGEMENT
    # =========================================================================

    def pause_all(self, reason: str = "Emergency pause") -> Dict[str, Any]:
        """Pause all active strategies"""
        with self._lock:
            paused = []
            for strategy_id, state in self._strategy_states.items():
                if state.status == StrategyStatus.ACTIVE:
                    self.pause_strategy(strategy_id, reason)
                    paused.append(strategy_id)

            self._is_active = False

            # Emit event
            self._emit_event(
                "all_strategies_paused",
                data={"reason": reason, "paused_count": len(paused)}
            )

            logger.warning(f"Paused all strategies: {reason}")

            return {
                "success": True,
                "paused_strategies": paused,
                "reason": reason
            }

    def resume_all(self) -> Dict[str, Any]:
        """Resume all paused strategies"""
        with self._lock:
            resumed = []
            for strategy_id, state in self._strategy_states.items():
                if state.status == StrategyStatus.PAUSED:
                    self.activate_strategy(strategy_id)
                    resumed.append(strategy_id)

            self._is_active = True

            # Emit event
            self._emit_event(
                "all_strategies_resumed",
                data={"resumed_count": len(resumed)}
            )

            logger.info(f"Resumed {len(resumed)} strategies")

            return {
                "success": True,
                "resumed_strategies": resumed
            }

    def reset_daily_pnl(self) -> None:
        """Reset daily PnL tracking (called at day boundary)"""
        with self._lock:
            self._today_pnl = 0.0

            for state in self._strategy_states.values():
                state.today_pnl = 0.0
                state.daily_loss_pct = 0.0

            self._current_day = datetime.now(timezone.utc).date()

            logger.info("Reset daily PnL tracking")

    # =========================================================================
    # EVENT HANDLING
    # =========================================================================

    def on_event(self, callback: Callable[[OrchestratorEvent], None]) -> None:
        """Register callback for orchestrator events"""
        self._event_callbacks.append(callback)

    def _emit_event(
        self,
        event_type: str,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Emit an orchestrator event"""
        event = OrchestratorEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            data=data or {},
            strategy_id=strategy_id,
            symbol=symbol
        )

        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    # =========================================================================
    # BACKGROUND TASKS
    # =========================================================================

    async def start_background_tasks(self) -> None:
        """Start background monitoring tasks"""
        # Metrics update task
        async def update_metrics():
            while self._is_active:
                try:
                    self._update_periodic_metrics()
                except Exception as e:
                    logger.error(f"Metrics update error: {e}")
                await asyncio.sleep(self.config.metrics_update_interval_seconds)

        # Cooldown check task
        async def check_cooldowns():
            while self._is_active:
                try:
                    self._check_cooldown_expiry()
                except Exception as e:
                    logger.error(f"Cooldown check error: {e}")
                await asyncio.sleep(60)  # Check every minute

        # Rebalancing check task
        async def check_rebalancing():
            while self._is_active:
                try:
                    if self._allocator.needs_rebalancing():
                        self.trigger_rebalance()
                except Exception as e:
                    logger.error(f"Rebalancing check error: {e}")
                await asyncio.sleep(300)  # Check every 5 minutes

        self._background_tasks = [
            asyncio.create_task(update_metrics()),
            asyncio.create_task(check_cooldowns()),
            asyncio.create_task(check_rebalancing())
        ]

        logger.info("Started background tasks")

    async def stop_background_tasks(self) -> None:
        """Stop background tasks"""
        for task in self._background_tasks:
            task.cancel()

        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        logger.info("Stopped background tasks")

    def _update_periodic_metrics(self) -> None:
        """Update metrics periodically"""
        # Check for day change
        today = datetime.now(timezone.utc).date()
        if self._current_day != today:
            self.reset_daily_pnl()

        self._last_metrics_update = datetime.now(timezone.utc)

    def _check_cooldown_expiry(self) -> None:
        """Check for strategies exiting cooldown"""
        with self._lock:
            for strategy_id, state in self._strategy_states.items():
                if state.status == StrategyStatus.COOLDOWN and not state.is_in_cooldown:
                    state.status = StrategyStatus.PAUSED
                    state.status_reason = "Cooldown expired, awaiting activation"
                    state.cooldown_until = None

                    logger.info(f"Strategy {strategy_id} exited cooldown")

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """Get complete orchestrator state for persistence"""
        with self._lock:
            return {
                "config": self.config.to_dict(),
                "strategy_states": {
                    sid: state.to_dict()
                    for sid, state in self._strategy_states.items()
                },
                "portfolio": {
                    "is_active": self._is_active,
                    "total_pnl": self._total_pnl,
                    "today_pnl": self._today_pnl,
                    "peak_equity": self._peak_equity,
                    "current_drawdown_pct": self._current_drawdown_pct
                },
                "allocation": self._allocator.get_state(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load orchestrator state from persistence"""
        with self._lock:
            if "portfolio" in state:
                portfolio = state["portfolio"]
                self._is_active = portfolio.get("is_active", True)
                self._total_pnl = portfolio.get("total_pnl", 0.0)
                self._today_pnl = portfolio.get("today_pnl", 0.0)
                self._peak_equity = portfolio.get("peak_equity", self.config.total_capital)
                self._current_drawdown_pct = portfolio.get("current_drawdown_pct", 0.0)

            if "allocation" in state:
                self._allocator.load_state(state["allocation"])

            logger.info("Loaded orchestrator state")


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global orchestrator instance
_strategy_orchestrator: Optional[StrategyOrchestrator] = None


def get_strategy_orchestrator(
    config: Optional[OrchestratorConfig] = None
) -> StrategyOrchestrator:
    """Get or create global strategy orchestrator instance"""
    global _strategy_orchestrator
    if _strategy_orchestrator is None:
        _strategy_orchestrator = StrategyOrchestrator(config)
    return _strategy_orchestrator


def reset_strategy_orchestrator() -> None:
    """Reset global strategy orchestrator instance"""
    global _strategy_orchestrator
    _strategy_orchestrator = None
    logger.info("Strategy orchestrator instance reset")
