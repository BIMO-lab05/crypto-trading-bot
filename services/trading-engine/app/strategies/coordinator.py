"""
Strategy Coordinator for Multi-Strategy Orchestration
=======================================================
Purpose: Coordinate signal flow from strategies through aggregation to execution

This module provides the central coordination layer that:
1. Receives signals from multiple strategies
2. Routes signals through appropriate aggregators
3. Manages risk budget across strategies
4. Prevents over-allocation and position conflicts
5. Provides strategy correlation analysis

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple, Callable
from threading import RLock
from collections import defaultdict
import statistics
import asyncio

from app.strategies.base import StrategyBase, StrategySignal, SignalType
from app.strategies.aggregator import (
    SignalAggregator,
    AggregatorConfig,
    AggregatedSignal,
    AggregationMethod,
    SignalDirection
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class CoordinatorConfig:
    """Configuration for Strategy Coordinator"""

    # Risk budget management
    total_risk_budget_pct: float = 10.0  # Total risk budget as % of capital
    max_risk_per_symbol_pct: float = 5.0  # Max risk per symbol
    max_risk_per_strategy_pct: float = 3.0  # Max risk per strategy
    max_correlated_exposure_pct: float = 8.0  # Max exposure for correlated strategies

    # Position limits
    max_concurrent_positions: int = 10  # Max open positions
    max_positions_per_symbol: int = 2  # Max positions per symbol
    max_positions_per_strategy: int = 5  # Max positions per strategy

    # Signal processing
    signal_batch_window_seconds: int = 5  # Batch signals within window
    signal_dedup_window_seconds: int = 60  # Deduplicate signals within window
    min_signal_interval_seconds: int = 30  # Min time between signals per symbol

    # Aggregation settings
    default_aggregation_method: AggregationMethod = AggregationMethod.WEIGHTED_AVERAGE
    require_aggregation_for_action: bool = True  # Require multiple strategies

    # Performance tracking
    strategy_performance_lookback_days: int = 30
    underperformer_threshold_sharpe: float = 0.0
    pause_underperformers: bool = True

    # Correlation settings
    high_correlation_threshold: float = 0.7
    reduce_correlated_allocation: bool = True
    correlation_reduction_factor: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_risk_budget_pct": self.total_risk_budget_pct,
            "max_risk_per_symbol_pct": self.max_risk_per_symbol_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "signal_batch_window_seconds": self.signal_batch_window_seconds,
            "default_aggregation_method": self.default_aggregation_method.value,
        }


# =============================================================================
# RISK BUDGET TRACKING
# =============================================================================

@dataclass
class RiskBudget:
    """Track risk budget usage"""
    total_budget_pct: float = 10.0
    used_pct: float = 0.0
    by_symbol: Dict[str, float] = field(default_factory=dict)
    by_strategy: Dict[str, float] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def available_pct(self) -> float:
        """Get available risk budget"""
        return max(0.0, self.total_budget_pct - self.used_pct)

    def allocate(
        self,
        symbol: str,
        strategy_id: str,
        risk_pct: float
    ) -> bool:
        """
        Allocate risk budget

        Returns True if allocation successful
        """
        if risk_pct > self.available_pct:
            return False

        self.used_pct += risk_pct
        self.by_symbol[symbol] = self.by_symbol.get(symbol, 0.0) + risk_pct
        self.by_strategy[strategy_id] = self.by_strategy.get(strategy_id, 0.0) + risk_pct
        self.last_updated = datetime.now(timezone.utc)

        return True

    def release(
        self,
        symbol: str,
        strategy_id: str,
        risk_pct: float
    ) -> None:
        """Release risk budget"""
        self.used_pct = max(0.0, self.used_pct - risk_pct)
        if symbol in self.by_symbol:
            self.by_symbol[symbol] = max(0.0, self.by_symbol[symbol] - risk_pct)
        if strategy_id in self.by_strategy:
            self.by_strategy[strategy_id] = max(0.0, self.by_strategy[strategy_id] - risk_pct)
        self.last_updated = datetime.now(timezone.utc)

    def get_symbol_usage(self, symbol: str) -> float:
        """Get risk budget usage for a symbol"""
        return self.by_symbol.get(symbol, 0.0)

    def get_strategy_usage(self, strategy_id: str) -> float:
        """Get risk budget usage for a strategy"""
        return self.by_strategy.get(strategy_id, 0.0)


# =============================================================================
# POSITION TRACKING
# =============================================================================

@dataclass
class TrackedPosition:
    """Track a position for coordination"""
    position_id: str
    symbol: str
    strategy_id: str
    side: str  # LONG or SHORT
    entry_price: float
    quantity: float
    risk_allocated_pct: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def position_value(self) -> float:
        """Get position value"""
        return self.entry_price * self.quantity


# =============================================================================
# STRATEGY COORDINATOR
# =============================================================================

class StrategyCoordinator:
    """
    Multi-Strategy Coordination Engine

    Coordinates the flow of signals from multiple strategies through
    aggregation and risk management to produce actionable trading decisions.

    Responsibilities:

    1. Signal Collection:
       - Receive signals from registered strategies
       - Batch signals within time windows
       - Deduplicate redundant signals

    2. Risk Budget Management:
       - Track overall portfolio risk
       - Enforce per-symbol risk limits
       - Enforce per-strategy risk limits
       - Prevent over-allocation

    3. Signal Aggregation:
       - Route signals to appropriate aggregators
       - Coordinate multi-strategy decisions
       - Handle conflicting signals

    4. Position Tracking:
       - Track open positions per strategy
       - Enforce position limits
       - Manage position conflicts

    5. Strategy Performance:
       - Track strategy performance
       - Identify underperformers
       - Adjust allocations based on performance

    6. Correlation Analysis:
       - Detect highly correlated strategies
       - Reduce exposure to correlated signals
       - Optimize diversification

    Usage:
        config = CoordinatorConfig()
        coordinator = StrategyCoordinator(config)

        # Register strategies
        coordinator.register_strategy(trend_strategy)
        coordinator.register_strategy(mean_reversion_strategy)

        # Submit signals
        signals = await strategy.generate_signals(symbol, analysis, price)
        for signal in signals:
            coordinator.submit_signal(signal)

        # Process and get aggregated decision
        decision = await coordinator.process_signals("BTCUSDT")

        # Record position
        if decision.is_actionable:
            coordinator.record_position_opened(position)
    """

    def __init__(
        self,
        config: Optional[CoordinatorConfig] = None,
        aggregator: Optional[SignalAggregator] = None
    ):
        """
        Initialize Strategy Coordinator

        Args:
            config: Coordinator configuration
            aggregator: Signal aggregator instance
        """
        self.config = config or CoordinatorConfig()
        self._lock = RLock()

        # Signal aggregator
        self._aggregator = aggregator or SignalAggregator(
            AggregatorConfig(default_method=self.config.default_aggregation_method)
        )

        # Strategy registry
        self._strategies: Dict[str, StrategyBase] = {}
        self._strategy_enabled: Dict[str, bool] = {}

        # Signal batching
        self._pending_signals: Dict[str, List[StrategySignal]] = defaultdict(list)
        self._last_signal_time: Dict[str, Dict[str, datetime]] = defaultdict(dict)

        # Risk budget
        self._risk_budget = RiskBudget(total_budget_pct=self.config.total_risk_budget_pct)

        # Position tracking
        self._open_positions: Dict[str, TrackedPosition] = {}
        self._position_count_by_symbol: Dict[str, int] = defaultdict(int)
        self._position_count_by_strategy: Dict[str, int] = defaultdict(int)

        # Performance tracking
        self._strategy_performance: Dict[str, Dict[str, float]] = {}

        # Correlation matrix
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}

        # Callbacks
        self._signal_callbacks: List[Callable] = []
        self._decision_callbacks: List[Callable] = []

        logger.info(
            f"StrategyCoordinator initialized: "
            f"risk_budget={self.config.total_risk_budget_pct}%, "
            f"max_positions={self.config.max_concurrent_positions}"
        )

    # =========================================================================
    # STRATEGY REGISTRATION
    # =========================================================================

    def register_strategy(
        self,
        strategy: StrategyBase,
        enabled: bool = True,
        performance: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Register a strategy with the coordinator

        Args:
            strategy: Strategy instance
            enabled: Whether strategy is enabled for trading
            performance: Optional performance metrics

        Returns:
            Registration result
        """
        with self._lock:
            strategy_id = strategy.strategy_id

            self._strategies[strategy_id] = strategy
            self._strategy_enabled[strategy_id] = enabled

            if performance:
                self._strategy_performance[strategy_id] = performance

            # Set weight in aggregator
            perf_score = performance.get("sharpe_ratio", 1.0) if performance else 1.0
            self._aggregator.set_strategy_weight(
                strategy_id,
                base_weight=1.0,
                performance=max(0.5, min(2.0, perf_score))
            )

            logger.info(f"Registered strategy: {strategy_id} (enabled={enabled})")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "enabled": enabled
            }

    def unregister_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """Unregister a strategy"""
        with self._lock:
            if strategy_id not in self._strategies:
                return {"success": False, "error": "Strategy not found"}

            del self._strategies[strategy_id]
            self._strategy_enabled.pop(strategy_id, None)
            self._strategy_performance.pop(strategy_id, None)

            logger.info(f"Unregistered strategy: {strategy_id}")

            return {"success": True, "strategy_id": strategy_id}

    def enable_strategy(self, strategy_id: str) -> None:
        """Enable a strategy for trading"""
        with self._lock:
            self._strategy_enabled[strategy_id] = True
            logger.info(f"Enabled strategy: {strategy_id}")

    def disable_strategy(self, strategy_id: str) -> None:
        """Disable a strategy from trading"""
        with self._lock:
            self._strategy_enabled[strategy_id] = False
            logger.info(f"Disabled strategy: {strategy_id}")

    def is_strategy_enabled(self, strategy_id: str) -> bool:
        """Check if a strategy is enabled"""
        return self._strategy_enabled.get(strategy_id, False)

    # =========================================================================
    # SIGNAL SUBMISSION
    # =========================================================================

    def submit_signal(self, signal: StrategySignal) -> Dict[str, Any]:
        """
        Submit a signal for coordination

        Args:
            signal: Strategy signal

        Returns:
            Submission result
        """
        with self._lock:
            strategy_id = signal.strategy_id
            symbol = signal.symbol

            # Check if strategy is enabled
            if not self._strategy_enabled.get(strategy_id, False):
                return {
                    "accepted": False,
                    "reason": f"Strategy {strategy_id} is disabled"
                }

            # Check for duplicate/too-recent signals
            last_time = self._last_signal_time.get(symbol, {}).get(strategy_id)
            if last_time:
                elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
                if elapsed < self.config.min_signal_interval_seconds:
                    return {
                        "accepted": False,
                        "reason": f"Signal too recent ({elapsed:.0f}s < {self.config.min_signal_interval_seconds}s)"
                    }

            # Check risk budget
            if signal.signal_type in [SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT]:
                if not self._check_risk_budget(symbol, strategy_id):
                    return {
                        "accepted": False,
                        "reason": "Risk budget exceeded"
                    }

                if not self._check_position_limits(symbol, strategy_id):
                    return {
                        "accepted": False,
                        "reason": "Position limits exceeded"
                    }

            # Add to pending signals
            self._pending_signals[symbol].append(signal)
            self._last_signal_time[symbol][strategy_id] = datetime.now(timezone.utc)

            # Add to aggregator
            self._aggregator.add_signal(signal)

            # Trigger callbacks
            for callback in self._signal_callbacks:
                try:
                    callback(signal)
                except Exception as e:
                    logger.error(f"Signal callback error: {e}")

            logger.debug(
                f"Signal submitted: {strategy_id} -> {symbol} "
                f"{signal.signal_type.value}"
            )

            return {
                "accepted": True,
                "signal_id": signal.signal_id,
                "pending_count": len(self._pending_signals[symbol])
            }

    def _check_risk_budget(self, symbol: str, strategy_id: str) -> bool:
        """Check if risk budget allows new position"""
        # Check overall budget
        if self._risk_budget.available_pct <= 0:
            return False

        # Check per-symbol limit
        if self._risk_budget.get_symbol_usage(symbol) >= self.config.max_risk_per_symbol_pct:
            return False

        # Check per-strategy limit
        if self._risk_budget.get_strategy_usage(strategy_id) >= self.config.max_risk_per_strategy_pct:
            return False

        return True

    def _check_position_limits(self, symbol: str, strategy_id: str) -> bool:
        """Check if position limits allow new position"""
        # Check total positions
        if len(self._open_positions) >= self.config.max_concurrent_positions:
            return False

        # Check positions per symbol
        if self._position_count_by_symbol.get(symbol, 0) >= self.config.max_positions_per_symbol:
            return False

        # Check positions per strategy
        if self._position_count_by_strategy.get(strategy_id, 0) >= self.config.max_positions_per_strategy:
            return False

        return True

    # =========================================================================
    # SIGNAL PROCESSING
    # =========================================================================

    async def process_signals(
        self,
        symbol: str,
        method: Optional[AggregationMethod] = None
    ) -> Optional[AggregatedSignal]:
        """
        Process pending signals for a symbol

        Args:
            symbol: Trading symbol
            method: Aggregation method

        Returns:
            Aggregated signal or None
        """
        with self._lock:
            pending = self._pending_signals.get(symbol, [])

            if not pending:
                return None

            # Check if we have enough signals
            if self.config.require_aggregation_for_action:
                if len(pending) < 2:
                    logger.debug(f"Insufficient signals for {symbol}: {len(pending)}")
                    return None

            # Aggregate signals
            result = self._aggregator.aggregate(
                symbol,
                method or self.config.default_aggregation_method
            )

            # Clear pending signals
            self._pending_signals[symbol] = []
            self._aggregator.clear(symbol)

            if result and result.is_actionable:
                # Apply correlation adjustment if needed
                if self.config.reduce_correlated_allocation:
                    result = self._apply_correlation_adjustment(result)

                # Trigger decision callbacks
                for callback in self._decision_callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        logger.error(f"Decision callback error: {e}")

                logger.info(
                    f"Processed signals for {symbol}: "
                    f"{result.action}, conf={result.confidence:.2f}"
                )

            return result

    async def process_all_pending(self) -> Dict[str, Optional[AggregatedSignal]]:
        """Process all pending signals for all symbols"""
        results = {}
        symbols = list(self._pending_signals.keys())

        for symbol in symbols:
            result = await self.process_signals(symbol)
            if result:
                results[symbol] = result

        return results

    def _apply_correlation_adjustment(
        self,
        signal: AggregatedSignal
    ) -> AggregatedSignal:
        """Adjust signal based on strategy correlations"""
        agreeing = signal.agreeing_strategies

        if len(agreeing) < 2:
            return signal

        # Check correlations between agreeing strategies
        high_correlation_count = 0

        for i, s1 in enumerate(agreeing):
            for s2 in agreeing[i+1:]:
                corr = self._correlation_matrix.get(s1, {}).get(s2, 0.0)
                if abs(corr) > self.config.high_correlation_threshold:
                    high_correlation_count += 1

        # Reduce confidence if many correlated strategies
        if high_correlation_count > 0:
            reduction = (
                self.config.correlation_reduction_factor *
                (high_correlation_count / len(agreeing))
            )
            signal.confidence *= (1 - reduction)
            signal.quality_score *= (1 - reduction)

            if signal.position_size_pct:
                signal.position_size_pct *= (1 - reduction)

            signal.reasoning += f" (Correlated strategy adjustment: -{reduction:.0%})"

        return signal

    # =========================================================================
    # POSITION MANAGEMENT
    # =========================================================================

    def record_position_opened(
        self,
        position_id: str,
        symbol: str,
        strategy_id: str,
        side: str,
        entry_price: float,
        quantity: float,
        risk_pct: float
    ) -> Dict[str, Any]:
        """
        Record a position being opened

        Args:
            position_id: Unique position identifier
            symbol: Trading symbol
            strategy_id: Strategy that generated the signal
            side: LONG or SHORT
            entry_price: Entry price
            quantity: Position quantity
            risk_pct: Risk allocated as percentage

        Returns:
            Recording result
        """
        with self._lock:
            # Allocate risk budget
            if not self._risk_budget.allocate(symbol, strategy_id, risk_pct):
                return {
                    "success": False,
                    "error": "Failed to allocate risk budget"
                }

            # Record position
            position = TrackedPosition(
                position_id=position_id,
                symbol=symbol,
                strategy_id=strategy_id,
                side=side,
                entry_price=entry_price,
                quantity=quantity,
                risk_allocated_pct=risk_pct
            )

            self._open_positions[position_id] = position
            self._position_count_by_symbol[symbol] += 1
            self._position_count_by_strategy[strategy_id] += 1

            logger.info(
                f"Position opened: {position_id} ({symbol} {side}), "
                f"risk={risk_pct}%"
            )

            return {
                "success": True,
                "position_id": position_id
            }

    def record_position_closed(
        self,
        position_id: str,
        exit_price: float,
        pnl: float
    ) -> Dict[str, Any]:
        """
        Record a position being closed

        Args:
            position_id: Position identifier
            exit_price: Exit price
            pnl: Profit/loss

        Returns:
            Recording result
        """
        with self._lock:
            if position_id not in self._open_positions:
                return {
                    "success": False,
                    "error": "Position not found"
                }

            position = self._open_positions[position_id]

            # Release risk budget
            self._risk_budget.release(
                position.symbol,
                position.strategy_id,
                position.risk_allocated_pct
            )

            # Update counters
            self._position_count_by_symbol[position.symbol] -= 1
            self._position_count_by_strategy[position.strategy_id] -= 1

            # Remove from tracking
            del self._open_positions[position_id]

            # Update strategy performance
            self._update_strategy_performance(position.strategy_id, pnl)

            logger.info(
                f"Position closed: {position_id}, PnL={pnl:+.2f}"
            )

            return {
                "success": True,
                "position_id": position_id,
                "pnl": pnl
            }

    def _update_strategy_performance(
        self,
        strategy_id: str,
        pnl: float
    ) -> None:
        """Update strategy performance after trade"""
        if strategy_id not in self._strategy_performance:
            self._strategy_performance[strategy_id] = {
                "total_pnl": 0.0,
                "trade_count": 0,
                "winning_trades": 0
            }

        perf = self._strategy_performance[strategy_id]
        perf["total_pnl"] += pnl
        perf["trade_count"] += 1
        if pnl > 0:
            perf["winning_trades"] += 1

        # Update aggregator weight
        win_rate = perf["winning_trades"] / max(1, perf["trade_count"])
        perf_score = 0.5 + win_rate  # Simple performance score

        self._aggregator.set_strategy_weight(
            strategy_id,
            performance=perf_score
        )

        # Check for underperformer
        if (self.config.pause_underperformers and
            perf["trade_count"] >= 10 and
            win_rate < 0.4):
            self.disable_strategy(strategy_id)
            logger.warning(
                f"Strategy {strategy_id} disabled due to underperformance "
                f"(win_rate={win_rate:.1%})"
            )

    # =========================================================================
    # CORRELATION MANAGEMENT
    # =========================================================================

    def update_correlation(
        self,
        strategy_1: str,
        strategy_2: str,
        correlation: float
    ) -> None:
        """Update correlation between two strategies"""
        with self._lock:
            if strategy_1 not in self._correlation_matrix:
                self._correlation_matrix[strategy_1] = {}
            if strategy_2 not in self._correlation_matrix:
                self._correlation_matrix[strategy_2] = {}

            self._correlation_matrix[strategy_1][strategy_2] = correlation
            self._correlation_matrix[strategy_2][strategy_1] = correlation

    def get_correlations(self) -> Dict[str, Dict[str, float]]:
        """Get correlation matrix"""
        with self._lock:
            return dict(self._correlation_matrix)

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def add_signal_callback(self, callback: Callable[[StrategySignal], None]) -> None:
        """Add callback for new signals"""
        self._signal_callbacks.append(callback)

    def add_decision_callback(self, callback: Callable[[AggregatedSignal], None]) -> None:
        """Add callback for trading decisions"""
        self._decision_callbacks.append(callback)

    # =========================================================================
    # STATE AND STATISTICS
    # =========================================================================

    def get_risk_budget_status(self) -> Dict[str, Any]:
        """Get current risk budget status"""
        with self._lock:
            return {
                "total_budget_pct": self._risk_budget.total_budget_pct,
                "used_pct": self._risk_budget.used_pct,
                "available_pct": self._risk_budget.available_pct,
                "by_symbol": dict(self._risk_budget.by_symbol),
                "by_strategy": dict(self._risk_budget.by_strategy)
            }

    def get_position_status(self) -> Dict[str, Any]:
        """Get current position status"""
        with self._lock:
            return {
                "total_positions": len(self._open_positions),
                "max_positions": self.config.max_concurrent_positions,
                "by_symbol": dict(self._position_count_by_symbol),
                "by_strategy": dict(self._position_count_by_strategy),
                "positions": [
                    {
                        "position_id": p.position_id,
                        "symbol": p.symbol,
                        "strategy_id": p.strategy_id,
                        "side": p.side,
                        "risk_pct": p.risk_allocated_pct
                    }
                    for p in self._open_positions.values()
                ]
            }

    def get_strategy_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all registered strategies"""
        with self._lock:
            return {
                sid: {
                    "enabled": self._strategy_enabled.get(sid, False),
                    "performance": self._strategy_performance.get(sid, {}),
                    "open_positions": self._position_count_by_strategy.get(sid, 0),
                    "risk_used_pct": self._risk_budget.get_strategy_usage(sid)
                }
                for sid in self._strategies
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get coordinator statistics"""
        with self._lock:
            return {
                "registered_strategies": len(self._strategies),
                "enabled_strategies": sum(1 for e in self._strategy_enabled.values() if e),
                "open_positions": len(self._open_positions),
                "risk_budget_used_pct": self._risk_budget.used_pct,
                "pending_signals": sum(len(s) for s in self._pending_signals.values()),
                "aggregator_stats": self._aggregator.get_stats()
            }

    def reset(self) -> None:
        """Reset coordinator state"""
        with self._lock:
            self._pending_signals.clear()
            self._last_signal_time.clear()
            self._risk_budget = RiskBudget(total_budget_pct=self.config.total_risk_budget_pct)
            self._open_positions.clear()
            self._position_count_by_symbol.clear()
            self._position_count_by_strategy.clear()
            self._aggregator.clear_all()
            logger.info("Coordinator state reset")


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_strategy_coordinator: Optional[StrategyCoordinator] = None


def get_strategy_coordinator(
    config: Optional[CoordinatorConfig] = None
) -> StrategyCoordinator:
    """Get or create global strategy coordinator instance"""
    global _strategy_coordinator
    if _strategy_coordinator is None:
        _strategy_coordinator = StrategyCoordinator(config)
    return _strategy_coordinator


def reset_strategy_coordinator() -> None:
    """Reset global strategy coordinator instance"""
    global _strategy_coordinator
    _strategy_coordinator = None
    logger.info("Strategy coordinator instance reset")
