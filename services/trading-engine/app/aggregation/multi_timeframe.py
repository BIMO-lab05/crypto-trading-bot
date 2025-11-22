"""
Multi-Timeframe Analyzer Module
Purpose: Analyze signals across multiple timeframes for better confirmation
Pattern: Phase 2 Enhancement - Multi-timeframe consensus

Timeframe Hierarchy:
- 15m (short-term): Entry/exit timing optimization
- 60m (medium-term): Primary trading signals (baseline)
- 240m (long-term): Trend direction confirmation

Alignment Scoring:
- All 3 agree (BUY/SELL): Very strong (+20% confidence boost)
- 2/3 agree: Moderate (no change)
- Split decision: Weak (-20% confidence penalty)
- Contradictory: Very weak (-40% confidence penalty)
"""

import logging
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass

from app.models import TradingSignal, SignalAction

logger = logging.getLogger(__name__)


class TimeframeWeight(Enum):
    """Weights for different timeframes in consensus calculation"""
    SHORT = 0.20   # 15m - 20% weight (timing)
    MEDIUM = 0.50  # 60m - 50% weight (primary)
    LONG = 0.30    # 240m - 30% weight (trend)


class AlignmentStrength(Enum):
    """Strength of timeframe alignment"""
    VERY_STRONG = "VERY_STRONG"    # All 3 agree on same direction
    STRONG = "STRONG"               # 2/3 agree, one HOLD
    MODERATE = "MODERATE"           # 2/3 agree, one disagrees
    WEAK = "WEAK"                   # All different or 2 HOLD
    CONTRADICTORY = "CONTRADICTORY" # 2 oppose each other (BUY vs SELL)


@dataclass
class TimeframeSignal:
    """Signal from a specific timeframe"""
    interval: str
    action: SignalAction
    confidence: float
    score: float
    weight: float


@dataclass
class MultiTimeframeAnalysis:
    """Result of multi-timeframe analysis"""
    primary_action: SignalAction      # Action from primary (60m) timeframe
    consensus_action: SignalAction     # Weighted consensus action
    alignment_strength: AlignmentStrength
    confidence_modifier: float         # Multiplier for confidence (0.6 to 1.2)
    timeframe_signals: Dict[str, TimeframeSignal]
    agreement_pct: float              # Percentage agreement (0-100)
    reasoning: str


class MultiTimeframeAnalyzer:
    """
    Analyzes trading signals across multiple timeframes

    Features:
    - Fetches signals from 15m, 60m, 240m timeframes
    - Calculates weighted consensus
    - Determines alignment strength
    - Applies confidence modifiers
    - Provides reasoning for decisions

    Integration:
    - Called AFTER individual signal aggregation
    - BEFORE final confidence adjustment
    - Modifies confidence based on timeframe alignment
    """

    def __init__(self):
        """Initialize multi-timeframe analyzer"""
        self.timeframes = ["15", "60", "240"]  # Minutes
        self.primary_timeframe = "60"  # Medium-term is primary

        # Timeframe weights
        self.weights = {
            "15": TimeframeWeight.SHORT.value,
            "60": TimeframeWeight.MEDIUM.value,
            "240": TimeframeWeight.LONG.value
        }

        # Statistics
        self.total_analyzed = 0
        self.alignment_counts = {
            AlignmentStrength.VERY_STRONG: 0,
            AlignmentStrength.STRONG: 0,
            AlignmentStrength.MODERATE: 0,
            AlignmentStrength.WEAK: 0,
            AlignmentStrength.CONTRADICTORY: 0
        }

        logger.info("MultiTimeframeAnalyzer initialized")
        logger.info(f"  Timeframes: {self.timeframes} minutes")
        logger.info(f"  Weights: 15m={self.weights['15']}, 60m={self.weights['60']}, 240m={self.weights['240']}")

    async def analyze_timeframes(
        self,
        signals: Dict[str, TradingSignal],
        primary_signal: TradingSignal
    ) -> MultiTimeframeAnalysis:
        """
        Analyze signals across multiple timeframes

        Args:
            signals: Dict of {interval: TradingSignal} for each timeframe
            primary_signal: The primary (60m) signal

        Returns:
            Multi-timeframe analysis with consensus and confidence modifier
        """
        self.total_analyzed += 1

        # Extract timeframe signals
        timeframe_signals = {}
        for interval, signal in signals.items():
            timeframe_signals[interval] = TimeframeSignal(
                interval=interval,
                action=signal.action,
                confidence=signal.confidence,
                score=signal.aggregated_score,
                weight=self.weights.get(interval, 0.0)
            )

        # Calculate consensus
        consensus_action = self._calculate_weighted_consensus(timeframe_signals)

        # Determine alignment strength
        alignment = self._determine_alignment(timeframe_signals)

        # Calculate confidence modifier
        confidence_modifier = self._calculate_confidence_modifier(alignment, timeframe_signals)

        # Calculate agreement percentage
        agreement_pct = self._calculate_agreement_percentage(timeframe_signals, consensus_action)

        # Generate reasoning
        reasoning = self._generate_reasoning(timeframe_signals, alignment, consensus_action)

        # Update statistics
        self.alignment_counts[alignment] += 1

        # Log analysis
        logger.info(f"🔍 Multi-Timeframe Analysis:")
        logger.info(f"   15m: {timeframe_signals.get('15').action.value if '15' in timeframe_signals else 'N/A'}")
        logger.info(f"   60m: {timeframe_signals.get('60').action.value if '60' in timeframe_signals else 'N/A'} (primary)")
        logger.info(f"   240m: {timeframe_signals.get('240').action.value if '240' in timeframe_signals else 'N/A'}")
        logger.info(f"   Consensus: {consensus_action.value}")
        logger.info(f"   Alignment: {alignment.value}")
        logger.info(f"   Confidence modifier: {confidence_modifier:.2f}x")
        logger.info(f"   Agreement: {agreement_pct:.1f}%")

        return MultiTimeframeAnalysis(
            primary_action=primary_signal.action,
            consensus_action=consensus_action,
            alignment_strength=alignment,
            confidence_modifier=confidence_modifier,
            timeframe_signals=timeframe_signals,
            agreement_pct=agreement_pct,
            reasoning=reasoning
        )

    def _calculate_weighted_consensus(
        self,
        timeframe_signals: Dict[str, TimeframeSignal]
    ) -> SignalAction:
        """
        Calculate weighted consensus action across timeframes

        Uses weighted voting:
        - Each timeframe contributes its score * weight
        - Positive score → BUY, Negative → SELL, Near zero → HOLD
        """
        weighted_score = 0.0
        total_weight = 0.0

        for interval, tf_signal in timeframe_signals.items():
            weight = tf_signal.weight
            score = tf_signal.score

            weighted_score += score * weight
            total_weight += weight

        # Normalize by total weight
        if total_weight > 0:
            consensus_score = weighted_score / total_weight
        else:
            consensus_score = 0.0

        # Convert score to action
        if consensus_score >= 0.3:
            return SignalAction.BUY
        elif consensus_score <= -0.3:
            return SignalAction.SELL
        else:
            return SignalAction.HOLD

    def _determine_alignment(
        self,
        timeframe_signals: Dict[str, TimeframeSignal]
    ) -> AlignmentStrength:
        """
        Determine strength of alignment between timeframes

        Logic:
        - VERY_STRONG: All 3 agree on BUY or SELL
        - STRONG: 2/3 agree, one HOLD
        - MODERATE: 2/3 agree, one disagrees
        - WEAK: No clear consensus
        - CONTRADICTORY: BUY and SELL in different timeframes
        """
        actions = [tf.action for tf in timeframe_signals.values()]

        buy_count = actions.count(SignalAction.BUY)
        sell_count = actions.count(SignalAction.SELL)
        hold_count = actions.count(SignalAction.HOLD)

        # All 3 agree
        if buy_count == 3 or sell_count == 3:
            return AlignmentStrength.VERY_STRONG

        # Contradictory (both BUY and SELL present)
        if buy_count > 0 and sell_count > 0:
            if buy_count == 1 and sell_count == 1:
                # 1 BUY, 1 SELL, 1 HOLD
                return AlignmentStrength.WEAK
            else:
                # 2 BUY + 1 SELL or 1 BUY + 2 SELL
                return AlignmentStrength.CONTRADICTORY

        # 2 agree on BUY or SELL
        if buy_count == 2 or sell_count == 2:
            if hold_count == 1:
                # 2 agree, one HOLD
                return AlignmentStrength.STRONG
            else:
                # 2 agree, one disagrees (impossible given contradictory check above)
                return AlignmentStrength.MODERATE

        # All HOLD or no clear pattern
        return AlignmentStrength.WEAK

    def _calculate_confidence_modifier(
        self,
        alignment: AlignmentStrength,
        timeframe_signals: Dict[str, TimeframeSignal]
    ) -> float:
        """
        Calculate confidence modifier based on alignment strength

        Modifiers:
        - VERY_STRONG: 1.2x (+20% boost)
        - STRONG: 1.1x (+10% boost)
        - MODERATE: 1.0x (no change)
        - WEAK: 0.8x (-20% penalty)
        - CONTRADICTORY: 0.6x (-40% penalty)
        """
        base_modifiers = {
            AlignmentStrength.VERY_STRONG: 1.2,
            AlignmentStrength.STRONG: 1.1,
            AlignmentStrength.MODERATE: 1.0,
            AlignmentStrength.WEAK: 0.8,
            AlignmentStrength.CONTRADICTORY: 0.6
        }

        modifier = base_modifiers.get(alignment, 1.0)

        # Additional boost if long-term (240m) trend aligns with consensus
        if "240" in timeframe_signals and "60" in timeframe_signals:
            long_term_action = timeframe_signals["240"].action
            medium_term_action = timeframe_signals["60"].action

            # If long-term and medium-term align (excluding HOLD)
            if long_term_action == medium_term_action and long_term_action != SignalAction.HOLD:
                modifier *= 1.05  # Small additional boost for trend alignment

        return min(1.3, max(0.5, modifier))  # Cap between 0.5x and 1.3x

    def _calculate_agreement_percentage(
        self,
        timeframe_signals: Dict[str, TimeframeSignal],
        consensus: SignalAction
    ) -> float:
        """Calculate percentage of timeframes agreeing with consensus"""
        if not timeframe_signals:
            return 0.0

        agreeing = sum(
            1 for tf in timeframe_signals.values()
            if tf.action == consensus
        )

        return (agreeing / len(timeframe_signals)) * 100

    def _generate_reasoning(
        self,
        timeframe_signals: Dict[str, TimeframeSignal],
        alignment: AlignmentStrength,
        consensus: SignalAction
    ) -> str:
        """Generate human-readable reasoning for the analysis"""
        # Build action summary
        actions_str = ", ".join([
            f"{interval}m: {tf.action.value}"
            for interval, tf in sorted(timeframe_signals.items())
        ])

        # Base reasoning
        if alignment == AlignmentStrength.VERY_STRONG:
            return f"All timeframes agree ({actions_str}) → Strong {consensus.value} signal"
        elif alignment == AlignmentStrength.STRONG:
            return f"2/3 timeframes align ({actions_str}) → Good {consensus.value} signal"
        elif alignment == AlignmentStrength.MODERATE:
            return f"Moderate agreement ({actions_str}) → Cautious {consensus.value}"
        elif alignment == AlignmentStrength.WEAK:
            return f"Weak alignment ({actions_str}) → Low confidence"
        else:  # CONTRADICTORY
            return f"Conflicting signals ({actions_str}) → High uncertainty"

    def get_stats(self) -> Dict:
        """Get analyzer statistics"""
        total = self.total_analyzed
        if total == 0:
            return {
                "total_analyzed": 0,
                "alignment_distribution": {}
            }

        return {
            "total_analyzed": total,
            "alignment_distribution": {
                strength.value: {
                    "count": count,
                    "percentage": (count / total * 100) if total > 0 else 0
                }
                for strength, count in self.alignment_counts.items()
            }
        }

    def reset_stats(self):
        """Reset statistics"""
        self.total_analyzed = 0
        for strength in self.alignment_counts:
            self.alignment_counts[strength] = 0
        logger.info("Multi-timeframe analyzer stats reset")


# Global instance
_multi_timeframe_analyzer: Optional[MultiTimeframeAnalyzer] = None


def get_multi_timeframe_analyzer() -> MultiTimeframeAnalyzer:
    """Get or create multi-timeframe analyzer instance"""
    global _multi_timeframe_analyzer
    if _multi_timeframe_analyzer is None:
        _multi_timeframe_analyzer = MultiTimeframeAnalyzer()
    return _multi_timeframe_analyzer


def reset_multi_timeframe_analyzer():
    """Reset multi-timeframe analyzer (for testing)"""
    global _multi_timeframe_analyzer
    _multi_timeframe_analyzer = None
