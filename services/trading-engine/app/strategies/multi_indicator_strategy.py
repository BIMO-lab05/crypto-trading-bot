"""
Multi-Indicator Consensus Strategy
Purpose: Combines multiple indicators for high-probability trades
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

logger = logging.getLogger(__name__)


class SignalStrength(Enum):
    """Signal strength classifications"""
    VERY_STRONG = "very_strong"  # 80-100% consensus
    STRONG = "strong"            # 65-80% consensus
    MODERATE = "moderate"        # 50-65% consensus
    WEAK = "weak"                # 35-50% consensus
    NONE = "none"                # <35% consensus


@dataclass
class IndicatorVote:
    """Individual indicator vote"""
    name: str
    signal: str  # "BUY", "SELL", "HOLD"
    confidence: float
    weight: float
    metadata: Dict


@dataclass
class StrategySignal:
    """Combined strategy signal"""
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float
    strength: SignalStrength
    consensus_score: float
    buy_votes: int
    sell_votes: int
    hold_votes: int
    total_votes: int
    weighted_score: float
    indicator_breakdown: List[IndicatorVote]
    reasoning: str

    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "confidence": round(self.confidence, 4),
            "strength": self.strength.value,
            "consensus_score": round(self.consensus_score, 4),
            "votes": {
                "buy": self.buy_votes,
                "sell": self.sell_votes,
                "hold": self.hold_votes,
                "total": self.total_votes
            },
            "weighted_score": round(self.weighted_score, 4),
            "reasoning": self.reasoning,
            "indicators": [
                {
                    "name": v.name,
                    "signal": v.signal,
                    "confidence": round(v.confidence, 4),
                    "weight": v.weight
                }
                for v in self.indicator_breakdown
            ]
        }


class MultiIndicatorStrategy:
    """
    Multi-Indicator Consensus Strategy

    Combines multiple indicator signals with weighted voting:

    Indicator Weights (totaling 100%):
    --------------------------------
    TREND INDICATORS (40%):
    - Trend Filter (EMA 50/200): 15%
    - Ichimoku Cloud: 15%
    - MACD: 10%

    MOMENTUM INDICATORS (35%):
    - RSI + Divergence: 12%
    - Squeeze Momentum: 12%
    - Stochastic: 11%

    VOLATILITY INDICATORS (15%):
    - Bollinger Bands: 8%
    - ATR State: 7%

    VOLUME INDICATORS (10%):
    - Volume Confirmation: 10%

    Signal Generation Rules:
    -----------------------
    1. Calculate weighted score from all indicators
    2. Apply trend filter as gatekeeper
    3. Require minimum consensus (3+ indicators)
    4. Apply volume confirmation penalty if weak
    5. Generate final signal with confidence
    """

    # Indicator weights (must sum to 1.0)
    INDICATOR_WEIGHTS = {
        # Trend (40%)
        "TREND_FILTER": 0.15,
        "ICHIMOKU": 0.15,
        "MACD": 0.10,

        # Momentum (35%)
        "RSI": 0.12,
        "RSI_DIVERGENCE": 0.12,
        "SQZMOM": 0.12,
        "STOCHASTIC": 0.11,

        # Volatility (15%)
        "BOLLINGER": 0.08,
        "ATR": 0.07,

        # Volume (10%)
        "VOLUME": 0.10,
    }

    # Minimum requirements
    MIN_CONSENSUS_RATIO = 0.40  # 40% of indicators must agree
    MIN_CONFIDENCE = 0.50       # Minimum 50% confidence
    MIN_WEIGHTED_SCORE = 0.15   # Minimum weighted score magnitude

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        min_consensus_ratio: float = 0.40,
        min_confidence: float = 0.50
    ):
        """
        Initialize multi-indicator strategy

        Args:
            weights: Custom indicator weights (optional)
            min_consensus_ratio: Minimum ratio of agreeing indicators
            min_confidence: Minimum confidence threshold
        """
        self.weights = weights or self.INDICATOR_WEIGHTS
        self.min_consensus_ratio = min_consensus_ratio
        self.min_confidence = min_confidence

        # Normalize weights to sum to 1.0
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total_weight}, normalizing to 1.0")
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

        logger.info(
            f"MultiIndicatorStrategy initialized: "
            f"min_consensus={min_consensus_ratio}, min_conf={min_confidence}"
        )

    def process_indicators(
        self,
        indicators: Dict[str, Dict]
    ) -> StrategySignal:
        """
        Process all indicators and generate combined signal

        Args:
            indicators: Dict of indicator name -> indicator data
                       Each indicator should have: signal, confidence, metadata

        Returns:
            StrategySignal with combined analysis
        """
        votes: List[IndicatorVote] = []
        weighted_sum = 0.0
        total_weight = 0.0
        buy_count = 0
        sell_count = 0
        hold_count = 0

        # Process each indicator
        for name, data in indicators.items():
            # Get weight for this indicator
            weight = self.weights.get(name, 0.05)  # Default 5% for unknown

            # Extract signal and confidence
            signal = data.get("signal", "HOLD").upper()
            confidence = float(data.get("confidence", 0.5))
            metadata = data.get("metadata", {})

            # Create vote
            vote = IndicatorVote(
                name=name,
                signal=signal,
                confidence=confidence,
                weight=weight,
                metadata=metadata
            )
            votes.append(vote)

            # Calculate weighted contribution
            if signal == "BUY":
                weighted_sum += weight * confidence
                buy_count += 1
            elif signal == "SELL":
                weighted_sum -= weight * confidence
                sell_count += 1
            else:
                hold_count += 1

            total_weight += weight

            logger.debug(
                f"  {name}: {signal} (conf={confidence:.2f}, weight={weight:.2f})"
            )

        # Calculate consensus metrics
        total_votes = buy_count + sell_count + hold_count
        weighted_score = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Determine action signals
        action_counts = {"BUY": buy_count, "SELL": sell_count, "HOLD": hold_count}
        max_action = max(action_counts, key=action_counts.get)
        max_count = action_counts[max_action]
        consensus_ratio = max_count / total_votes if total_votes > 0 else 0.0

        # Determine final action
        final_action, confidence, strength = self._determine_action(
            weighted_score=weighted_score,
            consensus_ratio=consensus_ratio,
            buy_count=buy_count,
            sell_count=sell_count,
            hold_count=hold_count,
            total_votes=total_votes
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(
            action=final_action,
            weighted_score=weighted_score,
            consensus_ratio=consensus_ratio,
            buy_count=buy_count,
            sell_count=sell_count,
            hold_count=hold_count,
            strength=strength
        )

        signal = StrategySignal(
            action=final_action,
            confidence=confidence,
            strength=strength,
            consensus_score=consensus_ratio,
            buy_votes=buy_count,
            sell_votes=sell_count,
            hold_votes=hold_count,
            total_votes=total_votes,
            weighted_score=weighted_score,
            indicator_breakdown=votes,
            reasoning=reasoning
        )

        logger.info(
            f"Strategy Signal: {final_action} "
            f"(conf={confidence:.2%}, strength={strength.value}, "
            f"score={weighted_score:+.3f}, consensus={consensus_ratio:.1%})"
        )

        return signal

    def _determine_action(
        self,
        weighted_score: float,
        consensus_ratio: float,
        buy_count: int,
        sell_count: int,
        hold_count: int,
        total_votes: int
    ) -> Tuple[str, float, SignalStrength]:
        """
        Determine final action based on all metrics

        Returns:
            Tuple of (action, confidence, strength)
        """
        # Check minimum consensus
        if consensus_ratio < self.min_consensus_ratio:
            logger.info(f"Consensus too low: {consensus_ratio:.1%} < {self.min_consensus_ratio:.1%}")
            return "HOLD", 0.5, SignalStrength.WEAK

        # Determine direction from weighted score
        if weighted_score >= self.MIN_WEIGHTED_SCORE:
            action = "BUY"
            base_confidence = min(abs(weighted_score) + 0.5, 1.0)
        elif weighted_score <= -self.MIN_WEIGHTED_SCORE:
            action = "SELL"
            base_confidence = min(abs(weighted_score) + 0.5, 1.0)
        else:
            # Weak signal
            action = "HOLD"
            base_confidence = 0.5 + (1.0 - abs(weighted_score))

        # Adjust confidence by consensus
        confidence = base_confidence * (0.5 + 0.5 * consensus_ratio)

        # Determine strength
        if consensus_ratio >= 0.80:
            strength = SignalStrength.VERY_STRONG
        elif consensus_ratio >= 0.65:
            strength = SignalStrength.STRONG
        elif consensus_ratio >= 0.50:
            strength = SignalStrength.MODERATE
        elif consensus_ratio >= 0.35:
            strength = SignalStrength.WEAK
        else:
            strength = SignalStrength.NONE

        # Apply minimum confidence check
        if confidence < self.min_confidence and action != "HOLD":
            logger.info(f"Confidence below threshold: {confidence:.2%} < {self.min_confidence:.2%}")
            action = "HOLD"
            strength = SignalStrength.WEAK

        return action, confidence, strength

    def _generate_reasoning(
        self,
        action: str,
        weighted_score: float,
        consensus_ratio: float,
        buy_count: int,
        sell_count: int,
        hold_count: int,
        strength: SignalStrength
    ) -> str:
        """Generate human-readable reasoning for the signal"""
        total = buy_count + sell_count + hold_count

        if action == "BUY":
            return (
                f"{strength.value.replace('_', ' ').title()} BUY signal: "
                f"{buy_count}/{total} indicators bullish ({consensus_ratio:.0%} consensus), "
                f"weighted score {weighted_score:+.2f}"
            )
        elif action == "SELL":
            return (
                f"{strength.value.replace('_', ' ').title()} SELL signal: "
                f"{sell_count}/{total} indicators bearish ({consensus_ratio:.0%} consensus), "
                f"weighted score {weighted_score:+.2f}"
            )
        else:
            return (
                f"HOLD - Mixed signals: {buy_count} buy, {sell_count} sell, {hold_count} neutral. "
                f"Consensus {consensus_ratio:.0%}, score {weighted_score:+.2f}"
            )

    def apply_filters(
        self,
        signal: StrategySignal,
        trend_filter: Optional[Dict] = None,
        volume_filter: Optional[Dict] = None
    ) -> StrategySignal:
        """
        Apply additional filters to the signal

        Args:
            signal: Base strategy signal
            trend_filter: Trend filter data (optional)
            volume_filter: Volume filter data (optional)

        Returns:
            Modified StrategySignal after filters
        """
        modified_confidence = signal.confidence
        modified_action = signal.action
        filter_notes = []

        # Apply trend filter (gatekeeper)
        if trend_filter:
            trend = trend_filter.get("trend", "NEUTRAL")
            trend_conf = trend_filter.get("confidence", 0.5)

            # Block counter-trend trades in strong trends
            if signal.action == "BUY" and trend == "BEARISH" and trend_conf >= 0.75:
                modified_action = "HOLD"
                modified_confidence *= 0.3
                filter_notes.append(f"Blocked: BUY against strong bearish trend")
            elif signal.action == "SELL" and trend == "BULLISH" and trend_conf >= 0.75:
                modified_action = "HOLD"
                modified_confidence *= 0.3
                filter_notes.append(f"Blocked: SELL against strong bullish trend")
            elif trend == "NEUTRAL":
                modified_confidence *= 0.9
                filter_notes.append(f"Neutral trend: slight penalty")

        # Apply volume filter (validator)
        if volume_filter:
            confirmed = volume_filter.get("confirmed", True)
            strength = volume_filter.get("strength", "MODERATE")

            if not confirmed:
                if strength == "WEAK":
                    modified_confidence *= 0.5
                    filter_notes.append(f"Weak volume: 50% penalty")
                elif strength == "MINIMAL":
                    modified_confidence *= 0.3
                    filter_notes.append(f"Minimal volume: 70% penalty")
                else:
                    modified_confidence *= 0.7
                    filter_notes.append(f"Unconfirmed volume: 30% penalty")

        # Update reasoning if filtered
        if filter_notes:
            modified_reasoning = signal.reasoning + " | Filters: " + "; ".join(filter_notes)
        else:
            modified_reasoning = signal.reasoning

        return StrategySignal(
            action=modified_action,
            confidence=modified_confidence,
            strength=signal.strength,
            consensus_score=signal.consensus_score,
            buy_votes=signal.buy_votes,
            sell_votes=signal.sell_votes,
            hold_votes=signal.hold_votes,
            total_votes=signal.total_votes,
            weighted_score=signal.weighted_score,
            indicator_breakdown=signal.indicator_breakdown,
            reasoning=modified_reasoning
        )


# Global instance
_strategy: Optional[MultiIndicatorStrategy] = None


def get_strategy() -> MultiIndicatorStrategy:
    """Get or create global strategy instance"""
    global _strategy
    if _strategy is None:
        _strategy = MultiIndicatorStrategy()
    return _strategy


def analyze_indicators(
    indicators: Dict[str, Dict],
    trend_filter: Optional[Dict] = None,
    volume_filter: Optional[Dict] = None
) -> Dict:
    """
    Convenience function to analyze indicators

    Args:
        indicators: Dict of indicator data
        trend_filter: Optional trend filter
        volume_filter: Optional volume filter

    Returns:
        Strategy signal as dict
    """
    strategy = get_strategy()
    signal = strategy.process_indicators(indicators)

    if trend_filter or volume_filter:
        signal = strategy.apply_filters(signal, trend_filter, volume_filter)

    return signal.to_dict()
