"""
Signal Conflict Resolver
=========================
Purpose: Handle conflicting signals from multiple trading strategies

When multiple strategies generate signals for the same symbol, they may
produce conflicting recommendations. The ConflictResolver determines
the final action using various resolution methods:

1. Weighted Voting: Weight signals by strategy performance/allocation
2. Priority-Based: Use signal from highest priority strategy
3. Strongest Signal: Use signal with highest confidence
4. Average: Average all signals for final direction
5. Unanimous: Only act if all strategies agree
6. Majority: Use signal with majority agreement
7. Veto: Any opposing signal cancels action

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import statistics
import uuid

from app.orchestration.models import (
    StrategySignal,
    AggregatedSignal,
    SignalDirection,
    ConflictResolutionMethod,
    StrategyConfig,
    StrategyState,
    StrategyPerformanceMetrics,
    StrategyAllocation,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFLICT RESOLVER CONFIGURATION
# =============================================================================

@dataclass
class ConflictResolverConfig:
    """
    Configuration for the Conflict Resolver

    Controls how conflicts are detected and resolved.
    """
    # Default resolution method
    default_method: ConflictResolutionMethod = ConflictResolutionMethod.WEIGHTED_VOTING

    # Per-symbol method overrides
    symbol_methods: Dict[str, ConflictResolutionMethod] = field(default_factory=dict)

    # Minimum agreement thresholds
    min_agreement_ratio: float = 0.5  # Min ratio for majority
    unanimous_threshold: float = 0.95  # Threshold for "unanimous" (allows small dissent)

    # Weighting parameters
    performance_weight: float = 0.4  # Weight performance in scoring
    allocation_weight: float = 0.3  # Weight allocation in scoring
    confidence_weight: float = 0.3  # Weight signal confidence in scoring

    # Signal quality thresholds
    min_signal_confidence: float = 0.3  # Ignore signals below this confidence
    min_strategies_for_action: int = 1  # Min strategies needed for action

    # Timing parameters
    signal_staleness_seconds: int = 300  # Signals older than this are stale
    merge_window_seconds: int = 60  # Window to merge similar signals

    # Conflict detection
    strength_conflict_threshold: float = 0.3  # Strength diff to consider conflict
    direction_conflict_penalty: float = 0.5  # Reduce quality score on conflict

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "default_method": self.default_method.value,
            "min_agreement_ratio": self.min_agreement_ratio,
            "min_signal_confidence": self.min_signal_confidence,
            "min_strategies_for_action": self.min_strategies_for_action,
            "signal_staleness_seconds": self.signal_staleness_seconds,
        }


# =============================================================================
# CONFLICT RESOLVER
# =============================================================================

class ConflictResolver:
    """
    Signal Conflict Resolution Engine

    Handles situations where multiple strategies generate conflicting
    signals for the same trading symbol. The resolver aggregates signals
    and determines the optimal action based on configurable methods.

    Conflict Detection:
    - Direction conflict: One strategy says LONG, another says SHORT
    - Strength conflict: Significant difference in signal strength
    - Timing conflict: Strategies disagree on entry timing

    Resolution Methods:

    1. Weighted Voting (default):
       - Weight each signal by strategy's performance and allocation
       - Higher performing strategies get more influence
       - Signals aggregated using weighted average

    2. Priority-Based:
       - Each strategy has a priority level (1-100)
       - When conflict occurs, higher priority wins
       - Useful for hierarchical strategy setups

    3. Strongest Signal:
       - Simply use the signal with highest confidence
       - Ignores strategy performance
       - Fast but potentially volatile

    4. Average:
       - Average all signal strengths
       - Direction from majority vote
       - Balances different views

    5. Unanimous:
       - Only act if all strategies agree on direction
       - Very conservative
       - May result in many "flat" signals

    6. Majority:
       - Direction decided by simple majority
       - Strength averaged from agreeing strategies
       - Democratic approach

    7. Veto:
       - Any opposing signal cancels action
       - Most conservative
       - Good for risk-averse setups

    Usage:
        resolver = ConflictResolver()

        # Register strategy info
        resolver.register_strategy("trend_following", config, state, performance)

        # Submit signals
        resolver.submit_signal(signal1)
        resolver.submit_signal(signal2)

        # Resolve conflicts
        aggregated = resolver.resolve_conflicts("BTCUSDT")

        # Clear for next cycle
        resolver.clear_symbol("BTCUSDT")
    """

    def __init__(self, config: Optional[ConflictResolverConfig] = None):
        """
        Initialize Conflict Resolver

        Args:
            config: Resolver configuration
        """
        self.config = config or ConflictResolverConfig()
        self._lock = RLock()

        # Signal storage by symbol
        self._pending_signals: Dict[str, List[StrategySignal]] = defaultdict(list)

        # Strategy data
        self._strategy_configs: Dict[str, StrategyConfig] = {}
        self._strategy_states: Dict[str, StrategyState] = {}
        self._strategy_performance: Dict[str, StrategyPerformanceMetrics] = {}
        self._strategy_allocations: Dict[str, StrategyAllocation] = {}

        # Resolution history
        self._resolution_history: List[AggregatedSignal] = []

        # Metrics
        self._conflicts_detected: int = 0
        self._conflicts_resolved: int = 0
        self._total_signals_processed: int = 0

        logger.info(
            f"ConflictResolver initialized: "
            f"method={self.config.default_method.value}"
        )

    # =========================================================================
    # STRATEGY REGISTRATION
    # =========================================================================

    def register_strategy(
        self,
        strategy_id: str,
        config: Optional[StrategyConfig] = None,
        state: Optional[StrategyState] = None,
        performance: Optional[StrategyPerformanceMetrics] = None,
        allocation: Optional[StrategyAllocation] = None
    ) -> None:
        """
        Register strategy information for conflict resolution

        Args:
            strategy_id: Strategy identifier
            config: Strategy configuration
            state: Current strategy state
            performance: Performance metrics
            allocation: Capital allocation
        """
        with self._lock:
            if config:
                self._strategy_configs[strategy_id] = config
            if state:
                self._strategy_states[strategy_id] = state
            if performance:
                self._strategy_performance[strategy_id] = performance
            if allocation:
                self._strategy_allocations[strategy_id] = allocation

    def update_strategy_data(
        self,
        strategy_id: str,
        state: Optional[StrategyState] = None,
        performance: Optional[StrategyPerformanceMetrics] = None,
        allocation: Optional[StrategyAllocation] = None
    ) -> None:
        """Update strategy data for better resolution decisions"""
        with self._lock:
            if state:
                self._strategy_states[strategy_id] = state
            if performance:
                self._strategy_performance[strategy_id] = performance
            if allocation:
                self._strategy_allocations[strategy_id] = allocation

    # =========================================================================
    # SIGNAL SUBMISSION
    # =========================================================================

    def submit_signal(self, signal: StrategySignal) -> Dict[str, Any]:
        """
        Submit a signal for conflict resolution

        Args:
            signal: Strategy signal to submit

        Returns:
            Submission result
        """
        with self._lock:
            # Validate signal
            if signal.confidence < self.config.min_signal_confidence:
                return {
                    "accepted": False,
                    "reason": f"Confidence {signal.confidence:.2f} below threshold {self.config.min_signal_confidence}"
                }

            # Check staleness
            age = (datetime.now(timezone.utc) - signal.timestamp).total_seconds()
            if age > self.config.signal_staleness_seconds:
                return {
                    "accepted": False,
                    "reason": f"Signal is stale ({age:.0f}s old)"
                }

            # Add to pending signals
            self._pending_signals[signal.symbol].append(signal)
            self._total_signals_processed += 1

            logger.debug(
                f"Signal submitted: {signal.strategy_id} -> {signal.symbol} "
                f"{signal.direction.value} (conf={signal.confidence:.2f})"
            )

            return {
                "accepted": True,
                "signal_id": signal.signal_id,
                "pending_count": len(self._pending_signals[signal.symbol])
            }

    def submit_signals(self, signals: List[StrategySignal]) -> Dict[str, Any]:
        """Submit multiple signals at once"""
        results = []
        for signal in signals:
            result = self.submit_signal(signal)
            results.append({
                "signal_id": signal.signal_id,
                **result
            })

        accepted = sum(1 for r in results if r["accepted"])
        return {
            "total": len(signals),
            "accepted": accepted,
            "rejected": len(signals) - accepted,
            "results": results
        }

    # =========================================================================
    # CONFLICT DETECTION
    # =========================================================================

    def detect_conflicts(self, symbol: str) -> Dict[str, Any]:
        """
        Detect conflicts among pending signals for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            Conflict analysis
        """
        with self._lock:
            signals = self._pending_signals.get(symbol, [])

            if len(signals) < 2:
                return {
                    "has_conflict": False,
                    "signal_count": len(signals),
                    "reason": "Insufficient signals for conflict"
                }

            # Group by direction
            directions = defaultdict(list)
            for signal in signals:
                directions[signal.direction].append(signal)

            # Check for direction conflict
            has_direction_conflict = (
                len(directions[SignalDirection.LONG]) > 0 and
                len(directions[SignalDirection.SHORT]) > 0
            )

            # Check for strength conflict
            strengths = [s.strength for s in signals if s.direction != SignalDirection.FLAT]
            has_strength_conflict = False
            if len(strengths) >= 2:
                strength_range = max(strengths) - min(strengths)
                has_strength_conflict = strength_range > self.config.strength_conflict_threshold

            # Analyze conflict details
            conflict_details = {
                "has_conflict": has_direction_conflict or has_strength_conflict,
                "signal_count": len(signals),
                "direction_conflict": has_direction_conflict,
                "strength_conflict": has_strength_conflict,
                "directions": {
                    d.value: len(sigs) for d, sigs in directions.items()
                },
                "strength_range": max(strengths) - min(strengths) if len(strengths) >= 2 else 0,
                "strategies_involved": [s.strategy_id for s in signals]
            }

            if conflict_details["has_conflict"]:
                self._conflicts_detected += 1
                logger.info(f"Conflict detected for {symbol}: {conflict_details}")

            return conflict_details

    # =========================================================================
    # CONFLICT RESOLUTION
    # =========================================================================

    def resolve_conflicts(
        self,
        symbol: str,
        method: Optional[ConflictResolutionMethod] = None
    ) -> Optional[AggregatedSignal]:
        """
        Resolve conflicts and produce aggregated signal

        Args:
            symbol: Trading symbol
            method: Resolution method (uses default if not specified)

        Returns:
            Aggregated signal or None if no action
        """
        with self._lock:
            signals = self._pending_signals.get(symbol, [])

            if not signals:
                return None

            if len(signals) < self.config.min_strategies_for_action:
                return None

            # Filter stale signals
            now = datetime.now(timezone.utc)
            fresh_signals = [
                s for s in signals
                if (now - s.timestamp).total_seconds() < self.config.signal_staleness_seconds
            ]

            if not fresh_signals:
                return None

            # Determine resolution method
            resolution_method = (
                method or
                self.config.symbol_methods.get(symbol) or
                self.config.default_method
            )

            # Apply resolution method
            if resolution_method == ConflictResolutionMethod.WEIGHTED_VOTING:
                result = self._resolve_weighted_voting(symbol, fresh_signals)
            elif resolution_method == ConflictResolutionMethod.PRIORITY_BASED:
                result = self._resolve_priority_based(symbol, fresh_signals)
            elif resolution_method == ConflictResolutionMethod.STRONGEST_SIGNAL:
                result = self._resolve_strongest_signal(symbol, fresh_signals)
            elif resolution_method == ConflictResolutionMethod.AVERAGE:
                result = self._resolve_average(symbol, fresh_signals)
            elif resolution_method == ConflictResolutionMethod.UNANIMOUS:
                result = self._resolve_unanimous(symbol, fresh_signals)
            elif resolution_method == ConflictResolutionMethod.MAJORITY:
                result = self._resolve_majority(symbol, fresh_signals)
            elif resolution_method == ConflictResolutionMethod.VETO:
                result = self._resolve_veto(symbol, fresh_signals)
            else:
                result = self._resolve_weighted_voting(symbol, fresh_signals)

            if result:
                self._conflicts_resolved += 1
                self._resolution_history.append(result)

                logger.info(
                    f"Resolved {symbol}: {result.direction.value} "
                    f"(method={resolution_method.value}, "
                    f"conf={result.aggregated_confidence:.2f})"
                )

            return result

    def _resolve_weighted_voting(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve using weighted voting

        Weights based on:
        - Strategy performance (Sharpe, win rate)
        - Capital allocation
        - Signal confidence
        """
        # Calculate weights for each signal
        weighted_signals = []
        for signal in signals:
            weight = self._calculate_signal_weight(signal)
            weighted_signals.append((signal, weight))

        # Calculate weighted vote for each direction
        direction_votes = defaultdict(float)
        direction_signals = defaultdict(list)
        total_weight = sum(w for _, w in weighted_signals)

        for signal, weight in weighted_signals:
            direction_votes[signal.direction] += weight
            direction_signals[signal.direction].append(signal)

        # Find winning direction
        if not direction_votes:
            return None

        winning_direction = max(direction_votes.keys(), key=lambda d: direction_votes[d])
        winning_signals = direction_signals[winning_direction]

        # Calculate aggregated strength and confidence
        if winning_signals:
            weights_winning = [
                self._calculate_signal_weight(s) for s in winning_signals
            ]
            total_winning_weight = sum(weights_winning)

            if total_winning_weight > 0:
                aggregated_strength = sum(
                    s.strength * w for s, w in zip(winning_signals, weights_winning)
                ) / total_winning_weight

                aggregated_confidence = sum(
                    s.confidence * w for s, w in zip(winning_signals, weights_winning)
                ) / total_winning_weight
            else:
                aggregated_strength = statistics.mean(s.strength for s in winning_signals)
                aggregated_confidence = statistics.mean(s.confidence for s in winning_signals)
        else:
            aggregated_strength = 0.0
            aggregated_confidence = 0.0

        # Calculate agreement ratio
        agreement_ratio = direction_votes[winning_direction] / total_weight if total_weight > 0 else 0

        # Detect conflict
        has_conflict = len(direction_votes) > 1 and any(
            d != winning_direction and d != SignalDirection.FLAT
            for d in direction_votes
        )

        # Calculate quality score
        quality_score = self._calculate_quality_score(
            agreement_ratio=agreement_ratio,
            has_conflict=has_conflict,
            confidence=aggregated_confidence,
            signal_count=len(signals)
        )

        # Determine action
        if winning_direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        # Find opposing strategies
        opposing = [
            s.strategy_id for s in signals
            if s.direction != winning_direction and s.direction != SignalDirection.FLAT
        ]

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=winning_direction,
            action=action,
            aggregated_strength=aggregated_strength,
            aggregated_confidence=aggregated_confidence,
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in winning_signals],
            opposing_strategies=opposing,
            resolution_method=ConflictResolutionMethod.WEIGHTED_VOTING,
            conflict_detected=has_conflict,
            resolution_reasoning=f"Weighted voting: {winning_direction.value} won with {agreement_ratio:.1%} of weight",
            suggested_position_size_pct=self._calculate_suggested_size(winning_signals),
            weighted_stop_loss_pct=self._calculate_weighted_stop_loss(winning_signals),
            weighted_take_profit_pct=self._calculate_weighted_take_profit(winning_signals),
            strategy_agreement_ratio=agreement_ratio,
            signal_quality_score=quality_score
        )

    def _resolve_priority_based(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve by selecting highest priority strategy's signal
        """
        # Get priority for each signal
        prioritized = []
        for signal in signals:
            config = self._strategy_configs.get(signal.strategy_id)
            priority = config.metadata.priority if config else 50
            prioritized.append((signal, priority))

        # Sort by priority (descending)
        prioritized.sort(key=lambda x: x[1], reverse=True)

        # Take highest priority signal
        winning_signal = prioritized[0][0]
        winning_priority = prioritized[0][1]

        # Check for conflict
        has_conflict = any(
            s.direction != winning_signal.direction and s.direction != SignalDirection.FLAT
            for s, _ in prioritized[1:]
        )

        # Calculate agreement
        agreeing = [
            s.strategy_id for s, _ in prioritized
            if s.direction == winning_signal.direction
        ]
        opposing = [
            s.strategy_id for s, _ in prioritized
            if s.direction != winning_signal.direction and s.direction != SignalDirection.FLAT
        ]

        agreement_ratio = len(agreeing) / len(signals)

        # Determine action
        if winning_signal.direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_signal.direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=winning_signal.direction,
            action=action,
            aggregated_strength=winning_signal.strength,
            aggregated_confidence=winning_signal.confidence,
            source_signals=signals,
            agreeing_strategies=agreeing,
            opposing_strategies=opposing,
            resolution_method=ConflictResolutionMethod.PRIORITY_BASED,
            conflict_detected=has_conflict,
            resolution_reasoning=f"Priority-based: {winning_signal.strategy_id} (priority={winning_priority}) selected",
            suggested_position_size_pct=winning_signal.position_size_pct or 5.0,
            weighted_stop_loss_pct=winning_signal.stop_loss_pct,
            weighted_take_profit_pct=winning_signal.take_profit_pct,
            strategy_agreement_ratio=agreement_ratio,
            signal_quality_score=winning_signal.confidence
        )

    def _resolve_strongest_signal(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve by selecting signal with highest confidence
        """
        # Sort by confidence
        sorted_signals = sorted(signals, key=lambda s: s.confidence, reverse=True)
        winning_signal = sorted_signals[0]

        # Check for conflict
        has_conflict = any(
            s.direction != winning_signal.direction and s.direction != SignalDirection.FLAT
            for s in sorted_signals[1:]
        )

        # Calculate agreement
        agreeing = [s.strategy_id for s in signals if s.direction == winning_signal.direction]
        opposing = [
            s.strategy_id for s in signals
            if s.direction != winning_signal.direction and s.direction != SignalDirection.FLAT
        ]

        # Determine action
        if winning_signal.direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_signal.direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=winning_signal.direction,
            action=action,
            aggregated_strength=winning_signal.strength,
            aggregated_confidence=winning_signal.confidence,
            source_signals=signals,
            agreeing_strategies=agreeing,
            opposing_strategies=opposing,
            resolution_method=ConflictResolutionMethod.STRONGEST_SIGNAL,
            conflict_detected=has_conflict,
            resolution_reasoning=f"Strongest signal: {winning_signal.strategy_id} (conf={winning_signal.confidence:.2f})",
            suggested_position_size_pct=winning_signal.position_size_pct or 5.0,
            weighted_stop_loss_pct=winning_signal.stop_loss_pct,
            weighted_take_profit_pct=winning_signal.take_profit_pct,
            strategy_agreement_ratio=len(agreeing) / len(signals),
            signal_quality_score=winning_signal.confidence
        )

    def _resolve_average(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve by averaging all signals
        """
        # Convert directions to numeric values
        direction_values = []
        for signal in signals:
            if signal.direction == SignalDirection.LONG:
                direction_values.append(1)
            elif signal.direction == SignalDirection.SHORT:
                direction_values.append(-1)
            else:
                direction_values.append(0)

        # Average direction
        avg_direction = statistics.mean(direction_values)

        # Determine final direction
        if avg_direction > 0.3:
            final_direction = SignalDirection.LONG
            action = "BUY"
        elif avg_direction < -0.3:
            final_direction = SignalDirection.SHORT
            action = "SELL"
        else:
            final_direction = SignalDirection.FLAT
            action = "HOLD"

        # Average strength and confidence
        avg_strength = statistics.mean(s.strength for s in signals)
        avg_confidence = statistics.mean(s.confidence for s in signals)

        # Detect conflict
        has_long = any(s.direction == SignalDirection.LONG for s in signals)
        has_short = any(s.direction == SignalDirection.SHORT for s in signals)
        has_conflict = has_long and has_short

        # Calculate agreement
        agreeing = [s.strategy_id for s in signals if s.direction == final_direction]
        opposing = [
            s.strategy_id for s in signals
            if s.direction != final_direction and s.direction != SignalDirection.FLAT
        ]

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=final_direction,
            action=action,
            aggregated_strength=avg_strength,
            aggregated_confidence=avg_confidence,
            source_signals=signals,
            agreeing_strategies=agreeing,
            opposing_strategies=opposing,
            resolution_method=ConflictResolutionMethod.AVERAGE,
            conflict_detected=has_conflict,
            resolution_reasoning=f"Average: direction_score={avg_direction:.2f}",
            suggested_position_size_pct=self._calculate_suggested_size(
                [s for s in signals if s.direction == final_direction]
            ),
            strategy_agreement_ratio=len(agreeing) / len(signals) if signals else 0,
            signal_quality_score=avg_confidence * (1 - abs(avg_direction))
        )

    def _resolve_unanimous(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve only if all strategies agree
        """
        # Filter out FLAT signals
        active_signals = [s for s in signals if s.direction != SignalDirection.FLAT]

        if not active_signals:
            return None

        # Check for unanimity
        directions = set(s.direction for s in active_signals)

        if len(directions) > 1:
            # Not unanimous - return FLAT
            return AggregatedSignal(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.FLAT,
                action="HOLD",
                aggregated_strength=0.0,
                aggregated_confidence=0.5,
                source_signals=signals,
                agreeing_strategies=[],
                opposing_strategies=[s.strategy_id for s in active_signals],
                resolution_method=ConflictResolutionMethod.UNANIMOUS,
                conflict_detected=True,
                resolution_reasoning="Unanimous: No agreement, staying flat",
                strategy_agreement_ratio=0.0,
                signal_quality_score=0.0
            )

        # All agree
        final_direction = active_signals[0].direction
        avg_strength = statistics.mean(s.strength for s in active_signals)
        avg_confidence = statistics.mean(s.confidence for s in active_signals)

        if final_direction == SignalDirection.LONG:
            action = "BUY"
        elif final_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=final_direction,
            action=action,
            aggregated_strength=avg_strength,
            aggregated_confidence=avg_confidence,
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in active_signals],
            opposing_strategies=[],
            resolution_method=ConflictResolutionMethod.UNANIMOUS,
            conflict_detected=False,
            resolution_reasoning=f"Unanimous: All {len(active_signals)} strategies agree on {final_direction.value}",
            suggested_position_size_pct=self._calculate_suggested_size(active_signals),
            strategy_agreement_ratio=1.0,
            signal_quality_score=avg_confidence
        )

    def _resolve_majority(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve by simple majority vote
        """
        # Count votes (exclude FLAT)
        votes = defaultdict(int)
        for signal in signals:
            if signal.direction != SignalDirection.FLAT:
                votes[signal.direction] += 1

        if not votes:
            return None

        # Find majority
        total_votes = sum(votes.values())
        winning_direction = max(votes.keys(), key=lambda d: votes[d])
        winning_votes = votes[winning_direction]

        # Check if majority achieved
        if winning_votes / total_votes < self.config.min_agreement_ratio:
            return AggregatedSignal(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.FLAT,
                action="HOLD",
                aggregated_strength=0.0,
                aggregated_confidence=0.3,
                source_signals=signals,
                agreeing_strategies=[],
                opposing_strategies=[s.strategy_id for s in signals],
                resolution_method=ConflictResolutionMethod.MAJORITY,
                conflict_detected=True,
                resolution_reasoning=f"Majority: No clear majority (best: {winning_votes}/{total_votes})",
                strategy_agreement_ratio=winning_votes / total_votes,
                signal_quality_score=0.0
            )

        # Calculate aggregated values from winning side
        winning_signals = [s for s in signals if s.direction == winning_direction]
        avg_strength = statistics.mean(s.strength for s in winning_signals)
        avg_confidence = statistics.mean(s.confidence for s in winning_signals)

        if winning_direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=winning_direction,
            action=action,
            aggregated_strength=avg_strength,
            aggregated_confidence=avg_confidence,
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in winning_signals],
            opposing_strategies=[
                s.strategy_id for s in signals
                if s.direction != winning_direction and s.direction != SignalDirection.FLAT
            ],
            resolution_method=ConflictResolutionMethod.MAJORITY,
            conflict_detected=len(votes) > 1,
            resolution_reasoning=f"Majority: {winning_direction.value} wins ({winning_votes}/{total_votes})",
            suggested_position_size_pct=self._calculate_suggested_size(winning_signals),
            strategy_agreement_ratio=winning_votes / total_votes,
            signal_quality_score=avg_confidence * (winning_votes / total_votes)
        )

    def _resolve_veto(
        self,
        symbol: str,
        signals: List[StrategySignal]
    ) -> Optional[AggregatedSignal]:
        """
        Resolve with veto power - any opposing signal cancels action
        """
        # Check for opposing signals
        has_long = any(s.direction == SignalDirection.LONG for s in signals)
        has_short = any(s.direction == SignalDirection.SHORT for s in signals)

        if has_long and has_short:
            # Veto triggered
            return AggregatedSignal(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.FLAT,
                action="HOLD",
                aggregated_strength=0.0,
                aggregated_confidence=0.5,
                source_signals=signals,
                agreeing_strategies=[],
                opposing_strategies=[s.strategy_id for s in signals],
                resolution_method=ConflictResolutionMethod.VETO,
                conflict_detected=True,
                resolution_reasoning="Veto: Opposing signals detected, action blocked",
                strategy_agreement_ratio=0.0,
                signal_quality_score=0.0
            )

        # No veto - use first non-flat direction
        active_signals = [s for s in signals if s.direction != SignalDirection.FLAT]

        if not active_signals:
            return None

        final_direction = active_signals[0].direction
        avg_strength = statistics.mean(s.strength for s in active_signals)
        avg_confidence = statistics.mean(s.confidence for s in active_signals)

        if final_direction == SignalDirection.LONG:
            action = "BUY"
        elif final_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction=final_direction,
            action=action,
            aggregated_strength=avg_strength,
            aggregated_confidence=avg_confidence,
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in active_signals],
            opposing_strategies=[],
            resolution_method=ConflictResolutionMethod.VETO,
            conflict_detected=False,
            resolution_reasoning=f"Veto: No opposition, proceeding with {final_direction.value}",
            suggested_position_size_pct=self._calculate_suggested_size(active_signals),
            strategy_agreement_ratio=1.0,
            signal_quality_score=avg_confidence
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_signal_weight(self, signal: StrategySignal) -> float:
        """Calculate weight for a signal based on strategy attributes"""
        strategy_id = signal.strategy_id

        # Start with base weight
        weight = 1.0

        # Add performance component
        if strategy_id in self._strategy_performance:
            perf = self._strategy_performance[strategy_id]
            # Normalize Sharpe to 0-1 scale
            sharpe_score = min(1.0, max(0.0, (perf.sharpe_ratio + 1) / 3))
            weight += sharpe_score * self.config.performance_weight

        # Add allocation component
        if strategy_id in self._strategy_allocations:
            alloc = self._strategy_allocations[strategy_id]
            # Normalize allocation to 0-1 scale (assuming max 50%)
            alloc_score = min(1.0, alloc.current_pct / 50)
            weight += alloc_score * self.config.allocation_weight

        # Add confidence component
        weight += signal.confidence * self.config.confidence_weight

        return weight

    def _calculate_quality_score(
        self,
        agreement_ratio: float,
        has_conflict: bool,
        confidence: float,
        signal_count: int
    ) -> float:
        """Calculate overall signal quality score"""
        # Base score from agreement and confidence
        score = agreement_ratio * 0.4 + confidence * 0.4

        # Add component for signal count (more signals = more reliable up to a point)
        signal_bonus = min(0.2, signal_count * 0.05)
        score += signal_bonus

        # Penalize for conflict
        if has_conflict:
            score *= (1 - self.config.direction_conflict_penalty)

        return min(1.0, max(0.0, score))

    def _calculate_suggested_size(self, signals: List[StrategySignal]) -> float:
        """Calculate suggested position size from signals"""
        sizes = [s.position_size_pct for s in signals if s.position_size_pct]
        if sizes:
            return statistics.mean(sizes)
        return 5.0  # Default 5%

    def _calculate_weighted_stop_loss(self, signals: List[StrategySignal]) -> Optional[float]:
        """Calculate weighted average stop loss"""
        stop_losses = [s.stop_loss_pct for s in signals if s.stop_loss_pct]
        if stop_losses:
            return statistics.mean(stop_losses)
        return None

    def _calculate_weighted_take_profit(self, signals: List[StrategySignal]) -> Optional[float]:
        """Calculate weighted average take profit"""
        take_profits = [s.take_profit_pct for s in signals if s.take_profit_pct]
        if take_profits:
            return statistics.mean(take_profits)
        return None

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def clear_symbol(self, symbol: str) -> None:
        """Clear pending signals for a symbol"""
        with self._lock:
            self._pending_signals[symbol] = []

    def clear_all(self) -> None:
        """Clear all pending signals"""
        with self._lock:
            self._pending_signals.clear()

    def get_pending_signals(self, symbol: str) -> List[StrategySignal]:
        """Get pending signals for a symbol"""
        with self._lock:
            return list(self._pending_signals.get(symbol, []))

    def get_all_pending_symbols(self) -> List[str]:
        """Get all symbols with pending signals"""
        with self._lock:
            return [s for s, sigs in self._pending_signals.items() if sigs]

    def get_resolution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get resolution history"""
        with self._lock:
            history = self._resolution_history[-limit:]
            return [r.to_dict() for r in history]

    def get_stats(self) -> Dict[str, Any]:
        """Get resolver statistics"""
        with self._lock:
            return {
                "total_signals_processed": self._total_signals_processed,
                "conflicts_detected": self._conflicts_detected,
                "conflicts_resolved": self._conflicts_resolved,
                "pending_symbols": len(self.get_all_pending_symbols()),
                "resolution_history_size": len(self._resolution_history),
                "registered_strategies": len(self._strategy_configs)
            }


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global resolver instance
_conflict_resolver: Optional[ConflictResolver] = None


def get_conflict_resolver(
    config: Optional[ConflictResolverConfig] = None
) -> ConflictResolver:
    """Get or create global conflict resolver instance"""
    global _conflict_resolver
    if _conflict_resolver is None:
        _conflict_resolver = ConflictResolver(config)
    return _conflict_resolver


def reset_conflict_resolver() -> None:
    """Reset global conflict resolver instance"""
    global _conflict_resolver
    _conflict_resolver = None
    logger.info("Conflict resolver instance reset")
