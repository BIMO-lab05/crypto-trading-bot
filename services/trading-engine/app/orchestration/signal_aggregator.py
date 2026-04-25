"""
Signal Aggregator
==================
Purpose: Collect, aggregate, and analyze trading signals from multiple strategies

The Signal Aggregator provides:
1. Signal collection from all active strategies
2. Timestamp and tagging of signals
3. Grouping signals by symbol
4. Conflict identification
5. Signal prioritization
6. Integration with ConflictResolver

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import uuid

from app.orchestration.models import (
    StrategySignal,
    AggregatedSignal,
    SignalDirection,
    ConflictResolutionMethod,
)
from app.orchestration.conflict_resolver import (
    ConflictResolver,
    ConflictResolverConfig,
    get_conflict_resolver,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# SIGNAL AGGREGATOR CONFIGURATION
# =============================================================================

@dataclass
class SignalAggregatorConfig:
    """
    Configuration for Signal Aggregator

    Controls signal collection, expiration, and conflict detection.
    """
    # Signal expiration
    signal_expiry_seconds: int = 300  # 5 minutes default

    # Signal filtering
    min_confidence: float = 0.3  # Minimum confidence to accept
    min_strength: float = 0.2  # Minimum strength to accept

    # Conflict thresholds
    strength_conflict_threshold: float = 0.3  # Difference to consider conflict
    confidence_conflict_threshold: float = 0.4  # Difference to consider conflict

    # Aggregation settings
    max_signals_per_symbol: int = 10  # Maximum signals to aggregate
    signal_merge_window_seconds: int = 60  # Window to merge similar signals

    # Prioritization weights
    priority_weight: float = 0.3  # Weight for strategy priority
    confidence_weight: float = 0.4  # Weight for signal confidence
    recency_weight: float = 0.3  # Weight for signal recency

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "signal_expiry_seconds": self.signal_expiry_seconds,
            "min_confidence": self.min_confidence,
            "min_strength": self.min_strength,
            "max_signals_per_symbol": self.max_signals_per_symbol,
        }


# =============================================================================
# SIGNAL METADATA
# =============================================================================

@dataclass
class SignalMetadata:
    """
    Additional metadata attached to signals during collection
    """
    collection_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_tag: str = ""
    batch_id: str = ""
    priority_score: float = 0.0
    is_actionable: bool = True
    conflict_flags: List[str] = field(default_factory=list)


# =============================================================================
# CONFLICT DETECTION RESULT
# =============================================================================

@dataclass
class ConflictDetectionResult:
    """
    Result of conflict detection for a symbol
    """
    symbol: str
    timestamp: datetime
    has_conflict: bool
    signal_count: int
    direction_conflict: bool = False
    strength_conflict: bool = False
    confidence_conflict: bool = False
    conflict_type: str = "none"
    conflicting_strategies: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "has_conflict": self.has_conflict,
            "signal_count": self.signal_count,
            "direction_conflict": self.direction_conflict,
            "strength_conflict": self.strength_conflict,
            "conflict_type": self.conflict_type,
            "conflicting_strategies": self.conflicting_strategies,
        }


# =============================================================================
# SIGNAL AGGREGATOR
# =============================================================================

class SignalAggregator:
    """
    Signal Collection and Aggregation Engine

    The SignalAggregator collects signals from multiple trading strategies
    and prepares them for conflict resolution. It provides:

    1. Signal Collection:
       - Receive signals from all active strategies
       - Validate signal parameters
       - Apply minimum thresholds
       - Tag with metadata

    2. Signal Organization:
       - Group signals by symbol
       - Sort by priority and confidence
       - Filter expired signals
       - Merge similar signals

    3. Conflict Detection:
       - Identify opposing directions
       - Detect significant strength differences
       - Flag overlapping position recommendations
       - Assess correlation conflicts

    4. Signal Prioritization:
       - Score signals based on multiple factors
       - Rank by priority, confidence, and recency
       - Support custom prioritization rules

    5. Integration:
       - Works with ConflictResolver for resolution
       - Feeds aggregated signals to execution
       - Provides analytics on signal patterns

    Usage:
        aggregator = SignalAggregator()

        # Collect signals
        aggregator.collect_signal(signal1)
        aggregator.collect_signal(signal2)

        # Check for conflicts
        conflicts = aggregator.detect_conflicts("BTCUSDT")

        # Get prioritized signals
        prioritized = aggregator.get_prioritized_signals("BTCUSDT")

        # Get aggregated result
        aggregated = aggregator.aggregate_signals("BTCUSDT")
    """

    def __init__(
        self,
        config: Optional[SignalAggregatorConfig] = None,
        conflict_resolver: Optional[ConflictResolver] = None
    ):
        """
        Initialize Signal Aggregator

        Args:
            config: Aggregator configuration
            conflict_resolver: Optional conflict resolver instance
        """
        self.config = config or SignalAggregatorConfig()
        self._conflict_resolver = conflict_resolver or get_conflict_resolver()
        self._lock = RLock()

        # Signal storage by symbol
        self._signals: Dict[str, List[Tuple[StrategySignal, SignalMetadata]]] = defaultdict(list)

        # Strategy priority mapping
        self._strategy_priorities: Dict[str, int] = {}

        # Collection statistics
        self._total_collected: int = 0
        self._total_rejected: int = 0
        self._total_expired: int = 0
        self._total_conflicts_detected: int = 0

        # Batch tracking
        self._current_batch_id: str = ""
        self._batch_count: int = 0

        # Conflict history
        self._conflict_history: List[ConflictDetectionResult] = []

        logger.info(
            f"SignalAggregator initialized: "
            f"expiry={self.config.signal_expiry_seconds}s, "
            f"min_confidence={self.config.min_confidence}"
        )

    # =========================================================================
    # SIGNAL COLLECTION
    # =========================================================================

    def collect_signal(
        self,
        signal: StrategySignal,
        source_tag: str = "",
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Collect a signal from a strategy

        Args:
            signal: Strategy signal to collect
            source_tag: Optional tag for signal source
            batch_id: Optional batch identifier

        Returns:
            Collection result
        """
        with self._lock:
            # Validate signal
            validation = self._validate_signal(signal)
            if not validation["valid"]:
                self._total_rejected += 1
                return {
                    "accepted": False,
                    "reason": validation["reason"],
                    "signal_id": signal.signal_id
                }

            # Check expiration
            if signal.is_expired:
                self._total_expired += 1
                return {
                    "accepted": False,
                    "reason": "Signal has expired",
                    "signal_id": signal.signal_id
                }

            # Create metadata
            metadata = SignalMetadata(
                collection_time=datetime.now(timezone.utc),
                source_tag=source_tag,
                batch_id=batch_id or self._current_batch_id,
                priority_score=self._calculate_priority_score(signal),
                is_actionable=signal.is_actionable
            )

            # Add to storage
            self._signals[signal.symbol].append((signal, metadata))
            self._total_collected += 1

            # Trim if exceeds limit
            if len(self._signals[signal.symbol]) > self.config.max_signals_per_symbol:
                # Remove oldest
                self._signals[signal.symbol].pop(0)

            # Forward to conflict resolver
            self._conflict_resolver.submit_signal(signal)

            logger.debug(
                f"Collected signal: {signal.strategy_id} -> {signal.symbol} "
                f"{signal.direction.value} (conf={signal.confidence:.2f})"
            )

            return {
                "accepted": True,
                "signal_id": signal.signal_id,
                "priority_score": metadata.priority_score,
                "pending_count": len(self._signals[signal.symbol])
            }

    def collect_signals_batch(
        self,
        signals: List[StrategySignal],
        source_tag: str = ""
    ) -> Dict[str, Any]:
        """
        Collect multiple signals in a batch

        Args:
            signals: List of signals to collect
            source_tag: Optional tag for signal source

        Returns:
            Batch collection result
        """
        with self._lock:
            # Generate batch ID
            batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            self._current_batch_id = batch_id
            self._batch_count += 1

            results = []
            accepted = 0
            rejected = 0

            for signal in signals:
                result = self.collect_signal(signal, source_tag, batch_id)
                results.append({
                    "signal_id": signal.signal_id,
                    "strategy_id": signal.strategy_id,
                    "symbol": signal.symbol,
                    **result
                })

                if result["accepted"]:
                    accepted += 1
                else:
                    rejected += 1

            return {
                "batch_id": batch_id,
                "total": len(signals),
                "accepted": accepted,
                "rejected": rejected,
                "results": results
            }

    def _validate_signal(self, signal: StrategySignal) -> Dict[str, Any]:
        """Validate signal against thresholds"""
        # Check confidence
        if signal.confidence < self.config.min_confidence:
            return {
                "valid": False,
                "reason": f"Confidence {signal.confidence:.2f} below minimum {self.config.min_confidence}"
            }

        # Check strength (for non-FLAT signals)
        if signal.direction != SignalDirection.FLAT:
            if abs(signal.strength) < self.config.min_strength:
                return {
                    "valid": False,
                    "reason": f"Strength {signal.strength:.2f} below minimum {self.config.min_strength}"
                }

        # Validate required fields
        if not signal.signal_id or not signal.strategy_id or not signal.symbol:
            return {
                "valid": False,
                "reason": "Missing required fields (signal_id, strategy_id, symbol)"
            }

        return {"valid": True, "reason": ""}

    def _calculate_priority_score(self, signal: StrategySignal) -> float:
        """Calculate priority score for signal ranking"""
        # Get strategy priority
        strategy_priority = self._strategy_priorities.get(signal.strategy_id, 50)
        normalized_priority = strategy_priority / 100.0

        # Calculate recency score (newer = higher)
        age_seconds = (datetime.now(timezone.utc) - signal.timestamp).total_seconds()
        max_age = self.config.signal_expiry_seconds
        recency_score = max(0, 1 - (age_seconds / max_age))

        # Weighted combination
        score = (
            normalized_priority * self.config.priority_weight +
            signal.confidence * self.config.confidence_weight +
            recency_score * self.config.recency_weight
        )

        return score

    # =========================================================================
    # CONFLICT DETECTION
    # =========================================================================

    def detect_conflicts(self, symbol: str) -> ConflictDetectionResult:
        """
        Detect conflicts among signals for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            ConflictDetectionResult
        """
        with self._lock:
            signals_with_meta = self._signals.get(symbol, [])
            signals = [s for s, _ in signals_with_meta]

            # Clean expired signals first
            self._clean_expired_signals(symbol)

            if len(signals) < 2:
                return ConflictDetectionResult(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    has_conflict=False,
                    signal_count=len(signals),
                    conflict_type="none"
                )

            # Group by direction
            directions = defaultdict(list)
            for signal in signals:
                directions[signal.direction].append(signal)

            # Check direction conflict (LONG vs SHORT)
            has_long = len(directions[SignalDirection.LONG]) > 0
            has_short = len(directions[SignalDirection.SHORT]) > 0
            direction_conflict = has_long and has_short

            # Check strength conflict
            non_flat_signals = [s for s in signals if s.direction != SignalDirection.FLAT]
            strength_conflict = False
            if len(non_flat_signals) >= 2:
                strengths = [s.strength for s in non_flat_signals]
                strength_range = max(strengths) - min(strengths)
                strength_conflict = strength_range > self.config.strength_conflict_threshold

            # Check confidence conflict
            confidence_conflict = False
            if len(signals) >= 2:
                confidences = [s.confidence for s in signals]
                confidence_range = max(confidences) - min(confidences)
                confidence_conflict = confidence_range > self.config.confidence_conflict_threshold

            # Determine conflict type
            has_conflict = direction_conflict or strength_conflict
            conflict_type = "none"
            if direction_conflict and strength_conflict:
                conflict_type = "direction_and_strength"
            elif direction_conflict:
                conflict_type = "direction"
            elif strength_conflict:
                conflict_type = "strength"

            # Get conflicting strategies
            conflicting_strategies = []
            if direction_conflict:
                long_strats = [s.strategy_id for s in directions[SignalDirection.LONG]]
                short_strats = [s.strategy_id for s in directions[SignalDirection.SHORT]]
                conflicting_strategies = long_strats + short_strats

            result = ConflictDetectionResult(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                has_conflict=has_conflict,
                signal_count=len(signals),
                direction_conflict=direction_conflict,
                strength_conflict=strength_conflict,
                confidence_conflict=confidence_conflict,
                conflict_type=conflict_type,
                conflicting_strategies=conflicting_strategies,
                details={
                    "long_count": len(directions[SignalDirection.LONG]),
                    "short_count": len(directions[SignalDirection.SHORT]),
                    "flat_count": len(directions[SignalDirection.FLAT]),
                }
            )

            if has_conflict:
                self._total_conflicts_detected += 1
                self._conflict_history.append(result)

                logger.info(
                    f"Conflict detected for {symbol}: {conflict_type} "
                    f"({len(signals)} signals from {len(set(s.strategy_id for s in signals))} strategies)"
                )

            return result

    def get_all_conflicts(self) -> Dict[str, ConflictDetectionResult]:
        """Get conflicts for all symbols with pending signals"""
        with self._lock:
            conflicts = {}
            for symbol in list(self._signals.keys()):
                conflict = self.detect_conflicts(symbol)
                if conflict.has_conflict:
                    conflicts[symbol] = conflict
            return conflicts

    # =========================================================================
    # SIGNAL PRIORITIZATION
    # =========================================================================

    def get_prioritized_signals(
        self,
        symbol: str,
        limit: Optional[int] = None
    ) -> List[Tuple[StrategySignal, float]]:
        """
        Get signals sorted by priority score

        Args:
            symbol: Trading symbol
            limit: Maximum signals to return

        Returns:
            List of (signal, priority_score) tuples
        """
        with self._lock:
            # Clean expired first
            self._clean_expired_signals(symbol)

            signals_with_meta = self._signals.get(symbol, [])

            # Calculate current priority scores
            scored = []
            for signal, metadata in signals_with_meta:
                # Recalculate score for freshness
                score = self._calculate_priority_score(signal)
                scored.append((signal, score))

            # Sort by score descending
            scored.sort(key=lambda x: x[1], reverse=True)

            if limit:
                scored = scored[:limit]

            return scored

    def get_highest_priority_signal(self, symbol: str) -> Optional[StrategySignal]:
        """Get the single highest priority signal for a symbol"""
        prioritized = self.get_prioritized_signals(symbol, limit=1)
        if prioritized:
            return prioritized[0][0]
        return None

    # =========================================================================
    # SIGNAL AGGREGATION
    # =========================================================================

    def aggregate_signals(
        self,
        symbol: str,
        method: Optional[ConflictResolutionMethod] = None
    ) -> Optional[AggregatedSignal]:
        """
        Aggregate all signals for a symbol using conflict resolution

        Args:
            symbol: Trading symbol
            method: Optional resolution method override

        Returns:
            AggregatedSignal or None
        """
        with self._lock:
            # Clean expired signals
            self._clean_expired_signals(symbol)

            # Delegate to conflict resolver
            return self._conflict_resolver.resolve_conflicts(symbol, method)

    def aggregate_all_symbols(
        self,
        method: Optional[ConflictResolutionMethod] = None
    ) -> Dict[str, AggregatedSignal]:
        """
        Aggregate signals for all symbols with pending signals

        Returns:
            Dictionary mapping symbol to aggregated signal
        """
        with self._lock:
            results = {}

            for symbol in list(self._signals.keys()):
                aggregated = self.aggregate_signals(symbol, method)
                if aggregated:
                    results[symbol] = aggregated

            return results

    # =========================================================================
    # SIGNAL MANAGEMENT
    # =========================================================================

    def _clean_expired_signals(self, symbol: str) -> int:
        """Remove expired signals for a symbol"""
        signals = self._signals.get(symbol, [])
        initial_count = len(signals)

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.config.signal_expiry_seconds)

        self._signals[symbol] = [
            (s, m) for s, m in signals
            if s.timestamp > cutoff and not s.is_expired
        ]

        removed = initial_count - len(self._signals[symbol])
        if removed > 0:
            self._total_expired += removed
            logger.debug(f"Cleaned {removed} expired signals for {symbol}")

        return removed

    def clean_all_expired(self) -> int:
        """Clean expired signals from all symbols"""
        with self._lock:
            total_removed = 0
            for symbol in list(self._signals.keys()):
                total_removed += self._clean_expired_signals(symbol)
            return total_removed

    def clear_symbol(self, symbol: str) -> None:
        """Clear all signals for a symbol"""
        with self._lock:
            if symbol in self._signals:
                del self._signals[symbol]
            # Also clear in conflict resolver
            self._conflict_resolver.clear_symbol(symbol)

    def clear_all(self) -> None:
        """Clear all signals"""
        with self._lock:
            self._signals.clear()
            self._conflict_resolver.clear_all()

    def set_strategy_priority(self, strategy_id: str, priority: int) -> None:
        """Set priority for a strategy (1-100)"""
        with self._lock:
            self._strategy_priorities[strategy_id] = max(1, min(100, priority))

    # =========================================================================
    # GETTERS AND STATS
    # =========================================================================

    def get_pending_signals(self, symbol: str) -> List[StrategySignal]:
        """Get all pending signals for a symbol"""
        with self._lock:
            self._clean_expired_signals(symbol)
            return [s for s, _ in self._signals.get(symbol, [])]

    def get_all_pending_symbols(self) -> List[str]:
        """Get all symbols with pending signals"""
        with self._lock:
            return [s for s in self._signals.keys() if self._signals[s]]

    def get_signal_count(self, symbol: Optional[str] = None) -> int:
        """Get count of pending signals"""
        with self._lock:
            if symbol:
                return len(self._signals.get(symbol, []))
            return sum(len(signals) for signals in self._signals.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregator statistics"""
        with self._lock:
            return {
                "total_collected": self._total_collected,
                "total_rejected": self._total_rejected,
                "total_expired": self._total_expired,
                "total_conflicts_detected": self._total_conflicts_detected,
                "pending_signals": self.get_signal_count(),
                "pending_symbols": len(self.get_all_pending_symbols()),
                "batch_count": self._batch_count,
                "current_batch_id": self._current_batch_id,
            }

    def get_conflict_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent conflict history"""
        with self._lock:
            history = self._conflict_history[-limit:]
            return [c.to_dict() for c in history]


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global signal aggregator instance
_signal_aggregator: Optional[SignalAggregator] = None


def get_signal_aggregator(
    config: Optional[SignalAggregatorConfig] = None
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
