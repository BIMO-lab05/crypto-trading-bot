"""
Signal Aggregator for Multi-Strategy Orchestration
====================================================
Purpose: Combine signals from multiple strategies into actionable decisions

This module provides sophisticated signal aggregation using multiple methods:
1. Majority Vote - Democratic decision based on signal count
2. Weighted Average - Weight by strategy performance/allocation
3. Confidence-Based Selection - Use highest confidence signal
4. Consensus - Require threshold agreement
5. Ensemble - Combine multiple aggregation methods

The aggregator handles:
- Signal normalization to common scale
- Conflicting signal resolution
- Signal strength calculation
- Position sizing recommendations
- Risk parameter aggregation

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from collections import defaultdict
import statistics
from uuid import uuid4

from app.strategies.base import (
    StrategySignal,
    SignalType,
    MarketCondition
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMERATIONS
# =============================================================================

class AggregationMethod(str, Enum):
    """Signal aggregation method"""
    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_AVERAGE = "weighted_average"
    CONFIDENCE_BASED = "confidence_based"
    CONSENSUS = "consensus"
    ENSEMBLE = "ensemble"
    STRONGEST_SIGNAL = "strongest_signal"
    UNANIMOUS = "unanimous"


class SignalDirection(str, Enum):
    """Normalized signal direction"""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class NormalizedSignal:
    """
    Normalized signal for aggregation

    Converts strategy-specific signals to a common format.
    """
    signal_id: str
    strategy_id: str
    symbol: str
    timestamp: datetime
    direction: SignalDirection
    strength: float  # -1.0 to +1.0
    confidence: float  # 0.0 to 1.0
    weight: float = 1.0  # Weight for aggregation
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    position_size_pct: Optional[float] = None
    original_signal: Optional[StrategySignal] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "strength": self.strength,
            "confidence": self.confidence,
            "weight": self.weight,
        }


@dataclass
class AggregatedSignal:
    """
    Result of signal aggregation

    Contains the combined decision from multiple strategies.
    """
    aggregation_id: str = field(default_factory=lambda: str(uuid4()))
    symbol: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Aggregated decision
    direction: SignalDirection = SignalDirection.NEUTRAL
    action: str = "HOLD"  # BUY, SELL, HOLD

    # Aggregated strength and confidence
    strength: float = 0.0  # -1.0 to +1.0
    confidence: float = 0.0  # 0.0 to 1.0
    agreement_ratio: float = 0.0  # Percentage of strategies agreeing

    # Aggregated risk parameters
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    position_size_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None

    # Source information
    source_signals: List[NormalizedSignal] = field(default_factory=list)
    agreeing_strategies: List[str] = field(default_factory=list)
    dissenting_strategies: List[str] = field(default_factory=list)

    # Aggregation metadata
    method_used: AggregationMethod = AggregationMethod.WEIGHTED_AVERAGE
    quality_score: float = 0.0
    is_actionable: bool = False
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "aggregation_id": self.aggregation_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "action": self.action,
            "strength": self.strength,
            "confidence": self.confidence,
            "agreement_ratio": self.agreement_ratio,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "position_size_pct": self.position_size_pct,
            "agreeing_strategies": self.agreeing_strategies,
            "dissenting_strategies": self.dissenting_strategies,
            "method_used": self.method_used.value,
            "quality_score": self.quality_score,
            "is_actionable": self.is_actionable,
            "reasoning": self.reasoning,
        }


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AggregatorConfig:
    """Configuration for Signal Aggregator"""

    # Default aggregation method
    default_method: AggregationMethod = AggregationMethod.WEIGHTED_AVERAGE

    # Threshold settings
    min_confidence_threshold: float = 0.4  # Min confidence to include signal
    min_agreement_ratio: float = 0.5  # Min agreement for action
    consensus_threshold: float = 0.7  # Threshold for consensus method

    # Strength thresholds
    strong_signal_threshold: float = 0.7  # Strength above this = strong
    weak_signal_threshold: float = 0.3  # Strength below this = weak

    # Weighting parameters
    performance_weight: float = 0.4  # Weight by strategy performance
    confidence_weight: float = 0.3  # Weight by signal confidence
    allocation_weight: float = 0.3  # Weight by capital allocation

    # Signal quality
    min_strategies_for_action: int = 2  # Min strategies needed
    max_signal_age_seconds: int = 300  # Max signal age to consider

    # Risk aggregation
    risk_aggregation: str = "weighted_average"  # mean, min, max, weighted
    position_size_aggregation: str = "min"  # Conservative position sizing

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "default_method": self.default_method.value,
            "min_confidence_threshold": self.min_confidence_threshold,
            "min_agreement_ratio": self.min_agreement_ratio,
            "consensus_threshold": self.consensus_threshold,
            "min_strategies_for_action": self.min_strategies_for_action,
        }


# =============================================================================
# SIGNAL AGGREGATOR
# =============================================================================

class SignalAggregator:
    """
    Multi-Strategy Signal Aggregator

    Combines trading signals from multiple strategies into unified
    trading decisions using various aggregation methods.

    Aggregation Methods:

    1. Majority Vote:
       - Each strategy gets one vote
       - Direction with most votes wins
       - Simple but ignores confidence and performance

    2. Weighted Average:
       - Weight signals by strategy performance and allocation
       - Better performing strategies have more influence
       - Most sophisticated default method

    3. Confidence-Based Selection:
       - Use signal from strategy with highest confidence
       - Fast decision, may miss consensus

    4. Consensus:
       - Require threshold agreement (e.g., 70%)
       - Conservative approach, fewer signals

    5. Ensemble:
       - Combine multiple methods
       - Use meta-voting across methods
       - Most robust but complex

    6. Strongest Signal:
       - Use signal with highest absolute strength
       - Aggressive approach

    7. Unanimous:
       - All strategies must agree
       - Very conservative

    Usage:
        config = AggregatorConfig(default_method=AggregationMethod.WEIGHTED_AVERAGE)
        aggregator = SignalAggregator(config)

        # Set strategy weights
        aggregator.set_strategy_weight("trend_following", 1.5, performance=1.2)
        aggregator.set_strategy_weight("mean_reversion", 1.0, performance=0.8)

        # Add signals
        aggregator.add_signal(signal_1)
        aggregator.add_signal(signal_2)

        # Aggregate
        result = aggregator.aggregate("BTCUSDT")

        # Clear for next cycle
        aggregator.clear("BTCUSDT")
    """

    def __init__(self, config: Optional[AggregatorConfig] = None):
        """
        Initialize Signal Aggregator

        Args:
            config: Aggregator configuration
        """
        self.config = config or AggregatorConfig()

        # Pending signals by symbol
        self._pending_signals: Dict[str, List[NormalizedSignal]] = defaultdict(list)

        # Strategy weights and performance
        self._strategy_weights: Dict[str, float] = {}
        self._strategy_performance: Dict[str, float] = {}
        self._strategy_allocations: Dict[str, float] = {}

        # Aggregation history
        self._aggregation_history: List[AggregatedSignal] = []

        # Statistics
        self._signals_processed: int = 0
        self._aggregations_performed: int = 0

        logger.info(
            f"SignalAggregator initialized: "
            f"method={self.config.default_method.value}"
        )

    # =========================================================================
    # STRATEGY WEIGHTS
    # =========================================================================

    def set_strategy_weight(
        self,
        strategy_id: str,
        base_weight: float = 1.0,
        performance: Optional[float] = None,
        allocation: Optional[float] = None
    ) -> None:
        """
        Set weight for a strategy

        Args:
            strategy_id: Strategy identifier
            base_weight: Base weight multiplier
            performance: Performance score (0-2, 1=average)
            allocation: Capital allocation percentage
        """
        self._strategy_weights[strategy_id] = base_weight
        if performance is not None:
            self._strategy_performance[strategy_id] = performance
        if allocation is not None:
            self._strategy_allocations[strategy_id] = allocation

        logger.debug(
            f"Set weight for {strategy_id}: "
            f"base={base_weight}, perf={performance}, alloc={allocation}"
        )

    def get_strategy_weight(self, strategy_id: str) -> float:
        """Get effective weight for a strategy"""
        base = self._strategy_weights.get(strategy_id, 1.0)
        perf = self._strategy_performance.get(strategy_id, 1.0)
        alloc = self._strategy_allocations.get(strategy_id, 0.1)

        # Combine weights
        effective = (
            base *
            (perf * self.config.performance_weight +
             1.0 * self.config.confidence_weight +
             (alloc / 10) * self.config.allocation_weight)  # Normalize allocation
        )

        return max(0.1, effective)

    # =========================================================================
    # SIGNAL SUBMISSION
    # =========================================================================

    def normalize_signal(self, signal: StrategySignal) -> NormalizedSignal:
        """
        Convert a strategy signal to normalized format

        Args:
            signal: Original strategy signal

        Returns:
            Normalized signal for aggregation
        """
        # Determine direction
        if signal.signal_type in [SignalType.ENTRY_LONG, SignalType.SCALE_IN]:
            direction = SignalDirection.LONG
            strength = abs(signal.strength) if signal.strength else signal.confidence
        elif signal.signal_type in [SignalType.ENTRY_SHORT]:
            direction = SignalDirection.SHORT
            strength = -abs(signal.strength) if signal.strength else -signal.confidence
        elif signal.signal_type in [SignalType.EXIT_LONG, SignalType.EXIT_SHORT]:
            direction = SignalDirection.NEUTRAL
            strength = 0.0
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.0

        # Calculate weight
        weight = self.get_strategy_weight(signal.strategy_id)

        return NormalizedSignal(
            signal_id=signal.signal_id,
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            timestamp=signal.timestamp,
            direction=direction,
            strength=strength,
            confidence=signal.confidence,
            weight=weight,
            stop_loss_pct=signal.stop_loss_pct,
            take_profit_pct=signal.take_profit_pct,
            position_size_pct=signal.position_size_pct,
            original_signal=signal
        )

    def add_signal(self, signal: StrategySignal) -> Dict[str, Any]:
        """
        Add a signal for aggregation

        Args:
            signal: Strategy signal to add

        Returns:
            Result dictionary
        """
        # Check confidence threshold
        if signal.confidence < self.config.min_confidence_threshold:
            return {
                "accepted": False,
                "reason": f"Confidence {signal.confidence:.2f} below threshold"
            }

        # Check signal age
        age = (datetime.now(timezone.utc) - signal.timestamp).total_seconds()
        if age > self.config.max_signal_age_seconds:
            return {
                "accepted": False,
                "reason": f"Signal too old ({age:.0f}s)"
            }

        # Normalize and add
        normalized = self.normalize_signal(signal)
        self._pending_signals[signal.symbol].append(normalized)
        self._signals_processed += 1

        logger.debug(
            f"Signal added: {signal.strategy_id} -> {signal.symbol} "
            f"{normalized.direction.value} (conf={signal.confidence:.2f})"
        )

        return {
            "accepted": True,
            "signal_id": signal.signal_id,
            "pending_count": len(self._pending_signals[signal.symbol])
        }

    def add_signals(self, signals: List[StrategySignal]) -> Dict[str, Any]:
        """Add multiple signals at once"""
        results = [self.add_signal(s) for s in signals]
        accepted = sum(1 for r in results if r.get("accepted"))
        return {
            "total": len(signals),
            "accepted": accepted,
            "rejected": len(signals) - accepted
        }

    # =========================================================================
    # SIGNAL AGGREGATION
    # =========================================================================

    def aggregate(
        self,
        symbol: str,
        method: Optional[AggregationMethod] = None
    ) -> Optional[AggregatedSignal]:
        """
        Aggregate pending signals for a symbol

        Args:
            symbol: Trading symbol
            method: Aggregation method (uses default if not specified)

        Returns:
            AggregatedSignal or None if insufficient signals
        """
        signals = self._pending_signals.get(symbol, [])

        if len(signals) < self.config.min_strategies_for_action:
            return None

        method = method or self.config.default_method

        # Call appropriate aggregation method
        if method == AggregationMethod.MAJORITY_VOTE:
            result = self._aggregate_majority_vote(symbol, signals)
        elif method == AggregationMethod.WEIGHTED_AVERAGE:
            result = self._aggregate_weighted_average(symbol, signals)
        elif method == AggregationMethod.CONFIDENCE_BASED:
            result = self._aggregate_confidence_based(symbol, signals)
        elif method == AggregationMethod.CONSENSUS:
            result = self._aggregate_consensus(symbol, signals)
        elif method == AggregationMethod.ENSEMBLE:
            result = self._aggregate_ensemble(symbol, signals)
        elif method == AggregationMethod.STRONGEST_SIGNAL:
            result = self._aggregate_strongest(symbol, signals)
        elif method == AggregationMethod.UNANIMOUS:
            result = self._aggregate_unanimous(symbol, signals)
        else:
            result = self._aggregate_weighted_average(symbol, signals)

        if result:
            result.method_used = method
            self._aggregation_history.append(result)
            self._aggregations_performed += 1

            logger.info(
                f"Aggregated {symbol}: {result.direction.value}, "
                f"strength={result.strength:.2f}, "
                f"confidence={result.confidence:.2f}, "
                f"agreement={result.agreement_ratio:.1%}"
            )

        return result

    def _aggregate_majority_vote(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate using majority vote"""
        # Count votes per direction
        votes = defaultdict(int)
        strategies_by_direction = defaultdict(list)

        for signal in signals:
            votes[signal.direction] += 1
            strategies_by_direction[signal.direction].append(signal.strategy_id)

        # Find winner
        total_votes = len(signals)
        winning_direction = max(votes.keys(), key=lambda d: votes[d])
        winning_votes = votes[winning_direction]
        agreement_ratio = winning_votes / total_votes

        # Check if meets threshold
        is_actionable = agreement_ratio >= self.config.min_agreement_ratio

        # Aggregate strength and confidence from winning signals
        winning_signals = [s for s in signals if s.direction == winning_direction]
        avg_strength = statistics.mean(s.strength for s in winning_signals)
        avg_confidence = statistics.mean(s.confidence for s in winning_signals)

        # Aggregate risk parameters
        sl, tp, pos_size = self._aggregate_risk_params(winning_signals)

        # Determine action
        if winning_direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            direction=winning_direction,
            action=action if is_actionable else "HOLD",
            strength=avg_strength,
            confidence=avg_confidence,
            agreement_ratio=agreement_ratio,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            position_size_pct=pos_size,
            risk_reward_ratio=tp / sl if sl and tp and sl > 0 else None,
            source_signals=signals,
            agreeing_strategies=strategies_by_direction[winning_direction],
            dissenting_strategies=[
                sid for d, sids in strategies_by_direction.items()
                for sid in sids if d != winning_direction
            ],
            quality_score=agreement_ratio * avg_confidence,
            is_actionable=is_actionable,
            reasoning=f"Majority vote: {winning_votes}/{total_votes} for {winning_direction.value}"
        )

    def _aggregate_weighted_average(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate using weighted average"""
        # Calculate weighted vote for each direction
        direction_weights = defaultdict(float)
        total_weight = sum(s.weight for s in signals)

        for signal in signals:
            direction_weights[signal.direction] += signal.weight

        # Find winning direction
        winning_direction = max(direction_weights.keys(), key=lambda d: direction_weights[d])
        winning_weight = direction_weights[winning_direction]
        agreement_ratio = winning_weight / total_weight if total_weight > 0 else 0

        # Get winning signals
        winning_signals = [s for s in signals if s.direction == winning_direction]

        # Weighted average of strength and confidence
        if winning_signals:
            total_win_weight = sum(s.weight for s in winning_signals)
            avg_strength = sum(s.strength * s.weight for s in winning_signals) / total_win_weight
            avg_confidence = sum(s.confidence * s.weight for s in winning_signals) / total_win_weight
        else:
            avg_strength = 0.0
            avg_confidence = 0.0

        # Aggregate risk parameters
        sl, tp, pos_size = self._aggregate_risk_params(winning_signals)

        # Check if actionable
        is_actionable = agreement_ratio >= self.config.min_agreement_ratio

        # Determine action
        if winning_direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            direction=winning_direction,
            action=action if is_actionable else "HOLD",
            strength=avg_strength,
            confidence=avg_confidence,
            agreement_ratio=agreement_ratio,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            position_size_pct=pos_size,
            risk_reward_ratio=tp / sl if sl and tp and sl > 0 else None,
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in winning_signals],
            dissenting_strategies=[s.strategy_id for s in signals if s.direction != winning_direction],
            quality_score=agreement_ratio * avg_confidence,
            is_actionable=is_actionable,
            reasoning=f"Weighted average: {winning_direction.value} with {agreement_ratio:.1%} weight"
        )

    def _aggregate_confidence_based(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate by selecting highest confidence signal"""
        # Find signal with highest confidence
        best_signal = max(signals, key=lambda s: s.confidence)

        # Calculate agreement
        same_direction = [s for s in signals if s.direction == best_signal.direction]
        agreement_ratio = len(same_direction) / len(signals)

        # Check if actionable
        is_actionable = (
            best_signal.confidence >= self.config.min_confidence_threshold and
            best_signal.direction != SignalDirection.NEUTRAL
        )

        # Determine action
        if best_signal.direction == SignalDirection.LONG:
            action = "BUY"
        elif best_signal.direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        return AggregatedSignal(
            symbol=symbol,
            direction=best_signal.direction,
            action=action if is_actionable else "HOLD",
            strength=best_signal.strength,
            confidence=best_signal.confidence,
            agreement_ratio=agreement_ratio,
            stop_loss_pct=best_signal.stop_loss_pct,
            take_profit_pct=best_signal.take_profit_pct,
            position_size_pct=best_signal.position_size_pct,
            risk_reward_ratio=(
                best_signal.take_profit_pct / best_signal.stop_loss_pct
                if best_signal.stop_loss_pct and best_signal.take_profit_pct
                else None
            ),
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in same_direction],
            dissenting_strategies=[s.strategy_id for s in signals if s.direction != best_signal.direction],
            quality_score=best_signal.confidence,
            is_actionable=is_actionable,
            reasoning=f"Confidence-based: {best_signal.strategy_id} (conf={best_signal.confidence:.2f})"
        )

    def _aggregate_consensus(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate requiring consensus threshold"""
        # Count directions
        direction_counts = defaultdict(int)
        for signal in signals:
            direction_counts[signal.direction] += 1

        total = len(signals)
        winning_direction = max(direction_counts.keys(), key=lambda d: direction_counts[d])
        agreement_ratio = direction_counts[winning_direction] / total

        # Check consensus threshold
        has_consensus = agreement_ratio >= self.config.consensus_threshold

        if has_consensus:
            # Use weighted average of consensus signals
            winning_signals = [s for s in signals if s.direction == winning_direction]
            return self._aggregate_weighted_average(symbol, winning_signals)
        else:
            # No consensus - return neutral
            return AggregatedSignal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                action="HOLD",
                strength=0.0,
                confidence=0.5,
                agreement_ratio=agreement_ratio,
                source_signals=signals,
                agreeing_strategies=[],
                dissenting_strategies=[s.strategy_id for s in signals],
                quality_score=0.0,
                is_actionable=False,
                reasoning=f"No consensus ({agreement_ratio:.1%} < {self.config.consensus_threshold:.1%})"
            )

    def _aggregate_ensemble(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate using ensemble of methods"""
        # Run multiple aggregation methods
        results = [
            self._aggregate_majority_vote(symbol, signals),
            self._aggregate_weighted_average(symbol, signals),
            self._aggregate_confidence_based(symbol, signals)
        ]

        # Vote among methods
        direction_votes = defaultdict(int)
        for result in results:
            if result.is_actionable:
                direction_votes[result.direction] += 1

        if not direction_votes:
            # No actionable signals from any method
            return AggregatedSignal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                action="HOLD",
                strength=0.0,
                confidence=0.0,
                agreement_ratio=0.0,
                source_signals=signals,
                is_actionable=False,
                reasoning="Ensemble: No method produced actionable signal"
            )

        # Find winning direction
        winning_direction = max(direction_votes.keys(), key=lambda d: direction_votes[d])
        winning_results = [r for r in results if r.direction == winning_direction and r.is_actionable]

        # Average the winning results
        avg_strength = statistics.mean(r.strength for r in winning_results)
        avg_confidence = statistics.mean(r.confidence for r in winning_results)
        avg_agreement = statistics.mean(r.agreement_ratio for r in winning_results)

        # Aggregate risk params from winning results
        all_sl = [r.stop_loss_pct for r in winning_results if r.stop_loss_pct]
        all_tp = [r.take_profit_pct for r in winning_results if r.take_profit_pct]

        sl = statistics.mean(all_sl) if all_sl else None
        tp = statistics.mean(all_tp) if all_tp else None

        # Determine action
        if winning_direction == SignalDirection.LONG:
            action = "BUY"
        elif winning_direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        methods_agree = len(winning_results)

        return AggregatedSignal(
            symbol=symbol,
            direction=winning_direction,
            action=action,
            strength=avg_strength,
            confidence=avg_confidence,
            agreement_ratio=avg_agreement,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            risk_reward_ratio=tp / sl if sl and tp and sl > 0 else None,
            source_signals=signals,
            agreeing_strategies=winning_results[0].agreeing_strategies if winning_results else [],
            dissenting_strategies=winning_results[0].dissenting_strategies if winning_results else [],
            quality_score=avg_confidence * (methods_agree / len(results)),
            is_actionable=True,
            reasoning=f"Ensemble: {methods_agree}/{len(results)} methods agree on {winning_direction.value}"
        )

    def _aggregate_strongest(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate by selecting strongest signal"""
        # Find signal with highest absolute strength
        best_signal = max(signals, key=lambda s: abs(s.strength))

        # Calculate agreement
        same_direction = [s for s in signals if s.direction == best_signal.direction]
        agreement_ratio = len(same_direction) / len(signals)

        # Determine action
        if best_signal.direction == SignalDirection.LONG:
            action = "BUY"
        elif best_signal.direction == SignalDirection.SHORT:
            action = "SELL"
        else:
            action = "HOLD"

        is_actionable = abs(best_signal.strength) >= self.config.strong_signal_threshold

        return AggregatedSignal(
            symbol=symbol,
            direction=best_signal.direction,
            action=action if is_actionable else "HOLD",
            strength=best_signal.strength,
            confidence=best_signal.confidence,
            agreement_ratio=agreement_ratio,
            stop_loss_pct=best_signal.stop_loss_pct,
            take_profit_pct=best_signal.take_profit_pct,
            position_size_pct=best_signal.position_size_pct,
            source_signals=signals,
            agreeing_strategies=[s.strategy_id for s in same_direction],
            dissenting_strategies=[s.strategy_id for s in signals if s.direction != best_signal.direction],
            quality_score=abs(best_signal.strength) * best_signal.confidence,
            is_actionable=is_actionable,
            reasoning=f"Strongest signal: {best_signal.strategy_id} (strength={best_signal.strength:.2f})"
        )

    def _aggregate_unanimous(
        self,
        symbol: str,
        signals: List[NormalizedSignal]
    ) -> AggregatedSignal:
        """Aggregate requiring unanimous agreement"""
        # Check if all signals agree
        active_signals = [s for s in signals if s.direction != SignalDirection.NEUTRAL]

        if not active_signals:
            return AggregatedSignal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                action="HOLD",
                is_actionable=False,
                source_signals=signals,
                reasoning="Unanimous: No active signals"
            )

        directions = set(s.direction for s in active_signals)

        if len(directions) == 1:
            # Unanimous agreement
            winning_direction = active_signals[0].direction
            avg_strength = statistics.mean(s.strength for s in active_signals)
            avg_confidence = statistics.mean(s.confidence for s in active_signals)

            sl, tp, pos_size = self._aggregate_risk_params(active_signals)

            if winning_direction == SignalDirection.LONG:
                action = "BUY"
            else:
                action = "SELL"

            return AggregatedSignal(
                symbol=symbol,
                direction=winning_direction,
                action=action,
                strength=avg_strength,
                confidence=avg_confidence,
                agreement_ratio=1.0,
                stop_loss_pct=sl,
                take_profit_pct=tp,
                position_size_pct=pos_size,
                source_signals=signals,
                agreeing_strategies=[s.strategy_id for s in active_signals],
                dissenting_strategies=[],
                quality_score=avg_confidence,
                is_actionable=True,
                reasoning=f"Unanimous: All {len(active_signals)} strategies agree on {winning_direction.value}"
            )
        else:
            # No unanimous agreement
            return AggregatedSignal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                action="HOLD",
                agreement_ratio=0.0,
                source_signals=signals,
                agreeing_strategies=[],
                dissenting_strategies=[s.strategy_id for s in signals],
                is_actionable=False,
                reasoning=f"Unanimous: Strategies disagree ({len(directions)} different directions)"
            )

    def _aggregate_risk_params(
        self,
        signals: List[NormalizedSignal]
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Aggregate risk parameters from signals"""
        sl_values = [s.stop_loss_pct for s in signals if s.stop_loss_pct]
        tp_values = [s.take_profit_pct for s in signals if s.take_profit_pct]
        pos_values = [s.position_size_pct for s in signals if s.position_size_pct]

        # Aggregate stop loss
        if sl_values:
            if self.config.risk_aggregation == "min":
                sl = min(sl_values)
            elif self.config.risk_aggregation == "max":
                sl = max(sl_values)
            else:
                sl = statistics.mean(sl_values)
        else:
            sl = None

        # Aggregate take profit
        if tp_values:
            if self.config.risk_aggregation == "min":
                tp = min(tp_values)
            elif self.config.risk_aggregation == "max":
                tp = max(tp_values)
            else:
                tp = statistics.mean(tp_values)
        else:
            tp = None

        # Aggregate position size (conservative by default)
        if pos_values:
            if self.config.position_size_aggregation == "min":
                pos_size = min(pos_values)
            elif self.config.position_size_aggregation == "max":
                pos_size = max(pos_values)
            else:
                pos_size = statistics.mean(pos_values)
        else:
            pos_size = None

        return sl, tp, pos_size

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def clear(self, symbol: str) -> None:
        """Clear pending signals for a symbol"""
        self._pending_signals[symbol] = []

    def clear_all(self) -> None:
        """Clear all pending signals"""
        self._pending_signals.clear()

    def get_pending_signals(self, symbol: str) -> List[NormalizedSignal]:
        """Get pending signals for a symbol"""
        return list(self._pending_signals.get(symbol, []))

    def get_pending_symbols(self) -> List[str]:
        """Get all symbols with pending signals"""
        return [s for s, sigs in self._pending_signals.items() if sigs]

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get aggregation history"""
        return [a.to_dict() for a in self._aggregation_history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregator statistics"""
        return {
            "signals_processed": self._signals_processed,
            "aggregations_performed": self._aggregations_performed,
            "pending_symbols": len(self.get_pending_symbols()),
            "strategy_weights": dict(self._strategy_weights),
            "history_size": len(self._aggregation_history)
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_signal_aggregator: Optional[SignalAggregator] = None


def get_signal_aggregator(
    config: Optional[AggregatorConfig] = None
) -> SignalAggregator:
    """Get or create global signal aggregator instance"""
    global _signal_aggregator
    if _signal_aggregator is None:
        _signal_aggregator = SignalAggregator(config)
    return _signal_aggregator


def reset_signal_aggregator() -> None:
    """Reset global signal aggregator instance"""
    global _signal_aggregator
    _signal_aggregator = None
    logger.info("Signal aggregator instance reset")
