"""
Signal Voter Module
Purpose: Voting and consensus logic for indicator aggregation
Pattern: Strangler Fig - Extracted from signal_aggregator.py
"""

import logging
from typing import Dict, Tuple
from app.models import IndicatorSignal, SignalAction

logger = logging.getLogger(__name__)


class SignalVoter:
    """
    VOTER: Calculates weighted scores and determines consensus

    Responsibilities:
    - Converts signals to numerical scores
    - Calculates weighted average of indicator signals
    - Counts BUY/SELL/HOLD votes
    - Determines consensus and preliminary action

    ADJUSTED FOR MORE AGGRESSIVE TRADING (2025-11-26):
    - Lowered aggregation_threshold from 0.2 to 0.15
    - Works with 6-7 voting indicators (RSI, MACD, BB, SMA, EMA, Trend, Stochastic)
    - Only needs 2/7 consensus (relaxed from 3/7)

    Voting Logic:
    - BUY -> +1.0
    - SELL -> -1.0
    - HOLD/NEUTRAL -> 0.0
    - Weighted by confidence
    """

    def __init__(self, aggregation_threshold: float = 0.05):
        """
        Initialize signal voter

        Args:
            aggregation_threshold: Score threshold for BUY/SELL decisions
                                  Scores >= +threshold -> BUY
                                  Scores <= -threshold -> SELL
                                  Scores in between -> HOLD

                                  LOWERED from 0.15 to 0.05 for AGGRESSIVE trading (2025-11-26)
                                  Any slight bias should trigger a trade
        """
        self.aggregation_threshold = aggregation_threshold
        logger.info(f"SignalVoter initialized with threshold={aggregation_threshold}")

    def signal_to_score(self, signal: SignalAction) -> float:
        """
        Convert signal action to numerical score

        Args:
            signal: Signal action (BUY/SELL/HOLD/NEUTRAL)

        Returns:
            Numerical score: +1.0 (BUY), -1.0 (SELL), 0.0 (HOLD/NEUTRAL)
        """
        if signal == SignalAction.BUY:
            return 1.0
        elif signal == SignalAction.SELL:
            return -1.0
        else:  # HOLD or NEUTRAL
            return 0.0

    def calculate_votes(
        self,
        voting_indicators: Dict[str, IndicatorSignal]
    ) -> Tuple[float, int, int, int, int]:
        """
        Calculate weighted scores and vote counts

        Args:
            voting_indicators: Dictionary of indicator signals to vote
                              (excludes GATEKEEPER and VALIDATOR)

        Returns:
            Tuple of (aggregated_score, consensus_count, buy_count, sell_count, hold_count)

        Algorithm:
        1. Convert each signal to score (-1.0 to +1.0)
        2. Weight by indicator confidence
        3. Calculate average weighted score
        4. Count votes by type
        5. Determine consensus (max count)
        """
        if not voting_indicators:
            logger.warning("No voting indicators provided")
            return 0.0, 0, 0, 0, 0

        weighted_scores = []
        buy_count = 0
        sell_count = 0
        hold_count = 0

        # Process each voting indicator
        for name, indicator in voting_indicators.items():
            # Convert signal to score
            score = self.signal_to_score(indicator.signal)

            # Weight by confidence
            weighted_score = score * indicator.confidence
            weighted_scores.append(weighted_score)

            # Count signals by type
            if indicator.signal == SignalAction.BUY:
                buy_count += 1
                logger.debug(f"  {name}: BUY (score: {weighted_score:+.2f})")
            elif indicator.signal == SignalAction.SELL:
                sell_count += 1
                logger.debug(f"  {name}: SELL (score: {weighted_score:+.2f})")
            else:
                hold_count += 1
                logger.debug(f"  {name}: HOLD (score: {weighted_score:+.2f})")

        # Calculate aggregated score (average of weighted scores)
        aggregated_score = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.0

        # Determine consensus count (max of buy/sell/hold counts)
        consensus_count = max(buy_count, sell_count, hold_count)

        logger.info(
            f"Voting Results: score={aggregated_score:+.2f}, "
            f"BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}, "
            f"consensus={consensus_count}/{len(voting_indicators)}"
        )

        return aggregated_score, consensus_count, buy_count, sell_count, hold_count

    def determine_action(
        self,
        aggregated_score: float
    ) -> Tuple[SignalAction, float]:
        """
        Determine preliminary action based on aggregated score

        Args:
            aggregated_score: Weighted average score from voting

        Returns:
            Tuple of (preliminary_action, preliminary_confidence)

        Logic (with AGGRESSIVE threshold of 0.05 as of 2025-11-26):
        - score >= +0.05 -> BUY with confidence = |score|
        - score <= -0.05 -> SELL with confidence = |score|
        - score in between -> HOLD with confidence = 1.0 - |score|
        """
        if aggregated_score >= self.aggregation_threshold:
            # BUY signal
            action = SignalAction.BUY
            confidence = min(abs(aggregated_score), 1.0)  # Cap at 1.0
            logger.info(f"Preliminary: BUY (score: {aggregated_score:+.2f}, conf: {confidence:.2f})")

        elif aggregated_score <= -self.aggregation_threshold:
            # SELL signal
            action = SignalAction.SELL
            confidence = min(abs(aggregated_score), 1.0)  # Cap at 1.0
            logger.info(f"Preliminary: SELL (score: {aggregated_score:+.2f}, conf: {confidence:.2f})")

        else:
            # Weak signal -> HOLD
            action = SignalAction.HOLD
            confidence = 1.0 - abs(aggregated_score)  # Higher confidence for scores near 0
            logger.info(f"Preliminary: HOLD (score: {aggregated_score:+.2f}, conf: {confidence:.2f})")

        return action, confidence

    def filter_non_voting_indicators(
        self,
        all_indicators: Dict[str, IndicatorSignal]
    ) -> Dict[str, IndicatorSignal]:
        """
        Filter out non-voting indicators (GATEKEEPER, VALIDATOR)

        Args:
            all_indicators: All fetched indicators

        Returns:
            Dictionary of voting indicators only

        Excluded from voting:
        - TREND_FILTER (GATEKEEPER) - filters, doesn't vote
        - VOLUME_CONFIRMATION (VALIDATOR) - validates, doesn't vote
        """
        voting_indicators = {
            k: v for k, v in all_indicators.items()
            if k not in ["TREND_FILTER", "VOLUME_CONFIRMATION"]
        }

        logger.info(f"Filtered voting indicators: {len(voting_indicators)}/{len(all_indicators)}")
        logger.debug(f"Voting: {list(voting_indicators.keys())}")
        logger.debug(f"Non-voting: {[k for k in all_indicators.keys() if k not in voting_indicators]}")

        return voting_indicators
