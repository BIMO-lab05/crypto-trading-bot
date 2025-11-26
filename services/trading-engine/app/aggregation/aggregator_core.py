"""
Core Aggregator Module
Purpose: Orchestrates signal aggregation using modular components
Pattern: Strangler Fig - Refactored from signal_aggregator.py
"""

import logging
from typing import Dict, Optional
from app.models import TradingSignal, IndicatorSignal, SignalAction
from app.config import get_settings

from .gatekeeper import TrendGatekeeper
from .validator import VolumeValidator
from .voter import SignalVoter
from .signal_cache import SignalCache

logger = logging.getLogger(__name__)


class CoreAggregator:
    """
    CORE AGGREGATOR: Orchestrates modular signal aggregation

    Responsibilities:
    - Coordinate gatekeeper, validator, and voter modules
    - Apply Phase 1 filtering logic
    - Enforce consensus requirements
    - Build final TradingSignal with metadata

    Phase 1 Pipeline:
    1. VOTER: Calculate preliminary signal from voting indicators
    2. GATEKEEPER: Block counter-trend trades
    3. VALIDATOR: Apply volume confidence penalty
    4. REQUIREMENTS: Check consensus and minimum confidence
    5. OUTPUT: Final TradingSignal

    Design Pattern: Strangler Fig
    - Replaces signal_aggregator.aggregate_signals() method
    - Uses composition over inheritance
    - Each module is independently testable
    """

    def __init__(self, settings=None):
        """
        Initialize core aggregator with modular components

        Args:
            settings: Application settings (optional, will use get_settings() if None)
        """
        self.settings = settings or get_settings()

        # Initialize modular components
        self.gatekeeper = TrendGatekeeper()
        self.validator = VolumeValidator()
        # AGGRESSIVE TRADING 2025-11-26: Very low threshold (0.05) for maximum sensitivity
        self.voter = SignalVoter(aggregation_threshold=0.05)
        self.cache = SignalCache(enabled=False)  # Disabled for now, Phase 2

        # Configuration - MAXIMUM AGGRESSIVE TRADING MODE (2025-11-26)
        # Changed to 1: Need only 1 indicator to agree
        self.min_consensus = 1
        # MAXIMUM AGGRESSIVE: Accept ANY signal - let score decide
        self.min_confidence = 0.01

        logger.info(
            f"CoreAggregator initialized "
            f"(min_consensus={self.min_consensus}, min_confidence={self.min_confidence})"
        )

    def aggregate_signals(
        self,
        indicators: Dict[str, IndicatorSignal],
        timestamp: int,
        atr_data: Optional[Dict] = None
    ) -> TradingSignal:
        """
        Aggregate individual indicator signals into a final trading signal

        Args:
            indicators: Dictionary of all fetched indicators
            timestamp: Signal timestamp (milliseconds)
            atr_data: ATR data for dynamic stops (optional)

        Returns:
            TradingSignal with final action, confidence, and metadata

        Pipeline:
        1. Filter voting indicators (exclude GATEKEEPER, VALIDATOR)
        2. Calculate votes and aggregated score
        3. Determine preliminary action and confidence
        4. Apply GATEKEEPER filter (trend blocking)
        5. Apply VALIDATOR penalty (volume confirmation)
        6. Check consensus requirements
        7. Build and return TradingSignal
        """
        symbol = "UNKNOWN"  # Will be set from context

        # Validate inputs
        if not indicators:
            logger.warning("No indicators available for aggregation")
            return self._build_error_signal(symbol, timestamp, "No indicators available")

        logger.info("="*80)
        logger.info("PHASE 1 SIGNAL AGGREGATION PIPELINE")
        logger.info("="*80)

        # ==================== STEP 1: Filter Voting Indicators ====================
        voting_indicators = self.voter.filter_non_voting_indicators(indicators)

        if not voting_indicators:
            logger.warning("No voting indicators available after filtering")
            return self._build_error_signal(symbol, timestamp, "No voting indicators")

        # ==================== STEP 2: Calculate Votes ====================
        aggregated_score, consensus_count, buy_count, sell_count, hold_count = \
            self.voter.calculate_votes(voting_indicators)

        # ==================== STEP 3: Determine Preliminary Action ====================
        action, confidence = self.voter.determine_action(aggregated_score)

        # ==================== STEP 4: Apply GATEKEEPER (Trend Filter) ====================
        trend_filter = indicators.get("TREND_FILTER")
        action, confidence, trend_blocked, trend_reason = \
            self.gatekeeper.check_signal(action, confidence, trend_filter)

        # ==================== STEP 5: Apply VALIDATOR (Volume Confirmation) ====================
        volume_conf = indicators.get("VOLUME_CONFIRMATION")
        confidence, volume_penalty, volume_reason = \
            self.validator.validate_volume(confidence, volume_conf)

        # ==================== STEP 6: Check Consensus Requirements ====================
        # RELAXED 2025-11-26: Now only requires 2 indicators instead of 3
        # RELAXED 2025-11-26: Confidence threshold lowered to 0.45 from 0.5
        meets_requirements = (
            consensus_count >= self.min_consensus and
            confidence >= self.min_confidence and
            not trend_blocked
        )

        if not meets_requirements:
            # Requirements not met -> Force to HOLD
            reasons = self._build_rejection_reasons(
                consensus_count,
                confidence,
                trend_blocked,
                trend_reason
            )
            logger.info(f"Requirements NOT met: {', '.join(reasons)}")
            action = SignalAction.HOLD
        else:
            logger.info(f"Requirements MET: Executing {action.value} signal")

        # ==================== STEP 7: Build Final Signal ====================
        metadata = self._build_metadata(
            buy_count, sell_count, hold_count,
            voting_indicators, meets_requirements,
            trend_blocked, trend_reason,
            volume_penalty, volume_reason,
            atr_data
        )

        logger.info(
            f"Final Signal: {action.value} "
            f"(score: {aggregated_score:+.2f}, conf: {confidence:.2f}, "
            f"consensus: {consensus_count}/{len(voting_indicators)})"
        )
        logger.info("="*80)

        return TradingSignal(
            symbol=symbol,
            timestamp=timestamp,
            action=action,
            confidence=round(confidence, 2),
            indicators=indicators,
            aggregated_score=round(aggregated_score, 3),
            consensus_count=consensus_count,
            metadata=metadata
        )

    def _build_error_signal(
        self,
        symbol: str,
        timestamp: int,
        error_message: str
    ) -> TradingSignal:
        """
        Build error signal when aggregation cannot proceed

        Args:
            symbol: Trading symbol
            timestamp: Signal timestamp
            error_message: Error description

        Returns:
            TradingSignal with HOLD action and error metadata
        """
        logger.error(f"Error signal: {error_message}")
        return TradingSignal(
            symbol=symbol,
            timestamp=timestamp,
            action=SignalAction.HOLD,
            confidence=0.0,
            indicators={},
            aggregated_score=0.0,
            consensus_count=0,
            metadata={"error": error_message}
        )

    def _build_rejection_reasons(
        self,
        consensus_count: int,
        confidence: float,
        trend_blocked: bool,
        trend_reason: str
    ) -> list:
        """
        Build list of reasons why signal was rejected

        Args:
            consensus_count: Number of indicators in consensus
            confidence: Signal confidence level
            trend_blocked: Whether signal was blocked by trend filter

        Returns:
            List of rejection reason strings
        """
        reasons = []

        if consensus_count < self.min_consensus:
            reasons.append(f"consensus={consensus_count} (min={self.min_consensus})")

        if confidence < self.min_confidence:
            reasons.append(f"confidence={confidence:.2f} (min={self.min_confidence})")

        if trend_blocked:
            reasons.append(f"trend_blocked: {trend_reason}")

        return reasons

    def _build_metadata(
        self,
        buy_count: int,
        sell_count: int,
        hold_count: int,
        voting_indicators: Dict[str, IndicatorSignal],
        meets_requirements: bool,
        trend_blocked: bool,
        trend_reason: str,
        volume_penalty: float,
        volume_reason: str,
        atr_data: Optional[Dict] = None
    ) -> Dict:
        """
        Build comprehensive metadata for TradingSignal

        Args:
            buy_count: Number of BUY votes
            sell_count: Number of SELL votes
            hold_count: Number of HOLD votes
            voting_indicators: Dictionary of voting indicators
            meets_requirements: Whether signal meets all requirements
            trend_blocked: Whether blocked by gatekeeper
            trend_reason: Gatekeeper reason
            volume_penalty: Validator penalty multiplier
            volume_reason: Validator reason
            atr_data: ATR data for dynamic stops (optional)

        Returns:
            Dictionary with complete signal metadata
        """
        metadata = {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "meets_requirements": meets_requirements,
            "phase_1_active": True,
            "trend_blocked": trend_blocked,
            "trend_reason": trend_reason,
            "volume_penalty": volume_penalty,
            "volume_reason": volume_reason,
            "voting_indicators_count": len(voting_indicators),
            # Add thresholds to metadata for debugging
            "min_consensus_required": self.min_consensus,
            "min_confidence_required": self.min_confidence
        }

        # Add ATR data for dynamic stops if available
        if atr_data:
            metadata["atr"] = atr_data
            logger.info(
                f"ATR Dynamic Stops: "
                f"SL={atr_data['stop_loss_long']:.2f}, "
                f"TP={atr_data['take_profit_long']:.2f}"
            )

        return metadata

    def get_aggregated_stats(self) -> Dict:
        """
        Get statistics from all aggregation components

        Returns:
            Dictionary with stats from gatekeeper, validator, and cache
        """
        return {
            "gatekeeper": self.gatekeeper.get_stats(),
            "validator": self.validator.get_stats(),
            "cache": self.cache.get_stats(),
            "thresholds": {
                "min_consensus": self.min_consensus,
                "min_confidence": self.min_confidence,
                "aggregation_threshold": self.voter.aggregation_threshold
            }
        }

    def reset_stats(self):
        """Reset statistics in all components"""
        self.gatekeeper.reset_stats()
        self.validator.reset_stats()
        logger.info("All aggregation stats reset")
