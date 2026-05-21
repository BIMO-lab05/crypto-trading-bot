"""
Signal Voter Module
Purpose: Voting and consensus logic for indicator aggregation
Pattern: Strangler Fig - Extracted from signal_aggregator.py

UPDATE 2025-11-26: Added weighted voting support for advanced indicators
- RSI Divergence: 1.2x weight (strong reversal signals)
- Ichimoku Cloud: 1.3x weight (multi-factor confirmation)
- Enhanced SQZMOM: 1.4x weight (high win-rate breakout signals)

UPDATE 2025-11-29: RESEARCH-BACKED CATEGORY CONSENSUS
Based on comprehensive research from Quantified Strategies, academic papers, and
top open-source bots (Freqtrade, Hummingbot, Jesse), implemented category-enforced
consensus to prevent using redundant indicators for confirmation.

Indicator Categories:
- MOMENTUM: RSI, MACD, STOCHASTIC, RSI_DIVERGENCE (measure same thing)
- TREND: SMA, EMA, ICHIMOKU (measure trend direction)
- VOLATILITY: BOLLINGER_BANDS, SQZMOM_ENHANCED (measure volatility)
- VOLUME: Already separate (VOLUME_CONFIRMATION is validator)

Research Finding: Using RSI + Stochastic + Williams %R gives redundant signals.
Optimal: Combine 1 momentum + 1 trend + volume confirmation.
"""

import logging
from typing import Dict, Tuple, Set
from app.models import IndicatorSignal, SignalAction
from app.aggregation.confidence_guard import validate_confidence

logger = logging.getLogger(__name__)

# Research-backed indicator categories (2025-11-29)
# Indicators in same category measure similar things - avoid counting multiple
INDICATOR_CATEGORIES = {
    # Momentum oscillators - all measure momentum/overbought/oversold
    "MOMENTUM": {"RSI", "MACD", "STOCHASTIC", "RSI_DIVERGENCE"},
    # Trend indicators - measure trend direction
    "TREND": {"SMA", "EMA", "ICHIMOKU"},
    # Volatility/Breakout indicators
    "VOLATILITY": {"BOLLINGER_BANDS", "SQZMOM_ENHANCED"},
}

# Research-backed indicator weights (2025-11-29)
# Based on backtested win rates and reliability
# ADJUSTED 2026-02-25: Reduced Ichimoku weight (1.2→0.9) to reduce SELL bias in ranging markets
RESEARCH_WEIGHTS = {
    # Highest reliability (research shows 40-73% win rates)
    "RSI": 1.0,
    "MACD": 1.0,
    "EMA": 1.0,
    "BOLLINGER_BANDS": 1.0,
    # Advanced with proven track record
    "RSI_DIVERGENCE": 1.3,  # Strong reversal detection
    "ICHIMOKU": 0.9,  # REDUCED: 1.2→0.9 (less weight in ranging/choppy markets)
    "SQZMOM_ENHANCED": 1.5,  # Highest win rate for breakouts (research: 92%)
    # Supporting indicators
    "SMA": 0.8,  # Lagging, less reliable alone
    "STOCHASTIC": 0.9,  # Good for timing, not direction
}


class SignalVoter:
    """
    VOTER: Calculates weighted scores and determines consensus

    Responsibilities:
    - Converts signals to numerical scores
    - Calculates weighted average of indicator signals
    - Supports indicator-specific weights for advanced indicators
    - Counts BUY/SELL/HOLD votes
    - Determines consensus and preliminary action

    UPDATED 2025-11-26:
    - Now supports 11 voting indicators (original 5 + Phase 1 + Advanced 3)
    - Advanced indicators have custom weights in metadata
    - Weighted voting gives more influence to high-quality signals

    Indicator Weights:
    - Standard indicators (RSI, MACD, BB, SMA, EMA, Stochastic): 1.0x
    - RSI Divergence: 1.2x (strong reversal detection)
    - Ichimoku Cloud: 1.3x (multi-factor trend confirmation)
    - Enhanced SQZMOM: 1.4x (high win-rate breakout signals)

    Voting Logic:
    - BUY -> +1.0
    - SELL -> -1.0
    - HOLD/NEUTRAL -> 0.0
    - Weighted by confidence AND indicator weight
    """

    def __init__(self, aggregation_threshold: float = 0.15):
        """
        Initialize signal voter

        Args:
            aggregation_threshold: Score threshold for BUY/SELL decisions
                                  Scores >= +threshold -> BUY
                                  Scores <= -threshold -> SELL
                                  Scores in between -> HOLD

                                  OPTIMIZED SETTINGS (2025-12-03):
                                  - 0.15 threshold requires stronger consensus (3x more selective)
                                  - Reduces false signals and improves win rate
                                  - Target: 55-60% win rate vs previous 41%
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

    def get_indicator_weight(self, indicator: IndicatorSignal) -> float:
        """
        Get the voting weight for an indicator

        Advanced indicators have custom weights stored in their metadata.
        Standard indicators have a default weight of 1.0.

        Args:
            indicator: The indicator signal

        Returns:
            Weight multiplier (1.0 for standard, >1.0 for advanced)
        """
        # Check if indicator has a custom weight in metadata
        if indicator.metadata and "weight" in indicator.metadata:
            return float(indicator.metadata["weight"])
        return 1.0

    def calculate_votes(
        self, voting_indicators: Dict[str, IndicatorSignal]
    ) -> Tuple[float, int, int, int, int]:
        """
        Calculate weighted scores and vote counts

        Args:
            voting_indicators: Dictionary of indicator signals to vote
                              (excludes GATEKEEPER and VALIDATOR)

        Returns:
            Tuple of (aggregated_score, consensus_count, buy_count, sell_count, hold_count)

        Algorithm (UPDATED 2025-11-26 for weighted voting):
        1. Convert each signal to score (-1.0 to +1.0)
        2. Apply indicator weight (advanced indicators have >1.0 weight)
        3. Weight by confidence
        4. Calculate weighted average score (normalized by total weights)
        5. Count votes by type
        6. Determine consensus (max count)
        """
        if not voting_indicators:
            logger.warning("No voting indicators provided")
            return 0.0, 0, 0, 0, 0

        weighted_scores = []
        total_weight = 0.0
        buy_count = 0
        sell_count = 0
        hold_count = 0

        # Process each voting indicator
        for name, indicator in voting_indicators.items():
            # Convert signal to score
            score = self.signal_to_score(indicator.signal)

            # Get indicator weight (advanced indicators have >1.0 weight)
            indicator_weight = self.get_indicator_weight(indicator)

            # Apply weight and confidence
            # Final score = base_score * confidence * indicator_weight
            weighted_score = score * indicator.confidence * indicator_weight
            weighted_scores.append(weighted_score)
            total_weight += indicator_weight

            # Count signals by type
            if indicator.signal == SignalAction.BUY:
                buy_count += 1
                if indicator_weight > 1.0:
                    logger.debug(
                        f"  {name}: BUY (score: {weighted_score:+.2f}, weight: {indicator_weight}x)"
                    )
                else:
                    logger.debug(f"  {name}: BUY (score: {weighted_score:+.2f})")
            elif indicator.signal == SignalAction.SELL:
                sell_count += 1
                if indicator_weight > 1.0:
                    logger.debug(
                        f"  {name}: SELL (score: {weighted_score:+.2f}, weight: {indicator_weight}x)"
                    )
                else:
                    logger.debug(f"  {name}: SELL (score: {weighted_score:+.2f})")
            else:
                hold_count += 1
                if indicator_weight > 1.0:
                    logger.debug(
                        f"  {name}: HOLD (score: {weighted_score:+.2f}, weight: {indicator_weight}x)"
                    )
                else:
                    logger.debug(f"  {name}: HOLD (score: {weighted_score:+.2f})")

        # Calculate aggregated score (normalized by total weight for fair comparison)
        # This ensures that adding more weighted indicators doesn't skew the score
        if total_weight > 0:
            aggregated_score = sum(weighted_scores) / total_weight
        else:
            aggregated_score = 0.0

        # Determine consensus count (max of buy/sell/hold counts)
        consensus_count = max(buy_count, sell_count, hold_count)

        logger.info(
            f"Voting Results: score={aggregated_score:+.2f}, "
            f"BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}, "
            f"consensus={consensus_count}/{len(voting_indicators)}, "
            f"total_weight={total_weight:.1f}"
        )

        return aggregated_score, consensus_count, buy_count, sell_count, hold_count

    def determine_action(self, aggregated_score: float) -> Tuple[SignalAction, float]:
        """
        Determine preliminary action based on aggregated score.

        Args:
            aggregated_score: Weighted average score from voting

        Returns:
            Tuple of (preliminary_action, preliminary_confidence)

        Logic:
        - score >= +threshold -> BUY with confidence = |score|  (legacy metric, see below)
        - score <= -threshold -> SELL with confidence = |score|  (legacy metric, see below)
        - score in between -> HOLD with confidence = 1.0 - |score|

        IMPORTANT (2026-05-20): The BUY/SELL confidence returned here is the
        *legacy* |weighted_score| metric. It is structurally bounded by the
        average indicator confidence — even unanimous agreement at avg conf
        0.5 caps at ~0.5 of the score range, so a 5-3 split lands at
        ~0.125. That made downstream confidence floors of 0.30+ structurally
        unreachable and produced 5+ months of zero fills.

        The CoreAggregator now overrides BUY/SELL confidence with
        `compute_agreement_confidence(voting_indicators, action)` which
        measures *agreement strength* (fraction of weighted voting power
        agreeing with the action × avg of their conviction). That value
        lives in [0, 1] with a realistic 0.3-0.8 distribution.

        This method retains the legacy formula so any direct callers
        (tests, alternate aggregators) still get a defined number;
        production behaviour comes from the override.
        """
        # validate_confidence rejects NaN/None/non-numeric and clamps to [0, 1].
        # Replaces the previous upper-only `min(abs(x), 1.0)` cap which let
        # negatives and NaN through.
        if aggregated_score >= self.aggregation_threshold:
            # BUY signal
            action = SignalAction.BUY
            confidence = validate_confidence(abs(aggregated_score), source="voter.BUY")
            logger.info(
                f"Preliminary: BUY (score: {aggregated_score:+.2f}, conf: {confidence:.2f})"
            )

        elif aggregated_score <= -self.aggregation_threshold:
            # SELL signal
            action = SignalAction.SELL
            confidence = validate_confidence(abs(aggregated_score), source="voter.SELL")
            logger.info(
                f"Preliminary: SELL (score: {aggregated_score:+.2f}, conf: {confidence:.2f})"
            )

        else:
            # Weak signal -> HOLD
            action = SignalAction.HOLD
            confidence = validate_confidence(
                1.0 - abs(aggregated_score), source="voter.HOLD"
            )
            logger.info(
                f"Preliminary: HOLD (score: {aggregated_score:+.2f}, conf: {confidence:.2f})"
            )

        return action, confidence

    def compute_agreement_confidence(
        self,
        voting_indicators: Dict[str, IndicatorSignal],
        action: SignalAction,
    ) -> float:
        """
        Compute agreement-based confidence for a non-HOLD action.

        New confidence metric (2026-05-20) replacing the legacy
        `|weighted_score|` approach used by `determine_action`.

        Formula:
            confidence = Σ_i (weight_i × conf_i)  for indicators agreeing with `action`
                       / Σ_j (weight_j)            for all voting indicators

        Range: [0, 1]. Realistic distribution in an 8-indicator basket:
          - All 8 agreeing at avg conf 0.5 → ~0.50
          - 6 agreeing at avg conf 0.5     → ~0.37
          - 5 agreeing at avg conf 0.5     → ~0.31
          - 4 agreeing at conf 0.7         → ~0.35
          - 3 agreeing at avg conf 0.5     → ~0.19
        The existing 0.30 `min_confidence` floor therefore translates to
        "≥ majority of weighted voting power agrees with mean conviction
        ≥ ~0.5". That matches the operator-intended semantics — quality
        gate that bites without being structurally unreachable.

        Why this is correct:
        - Decouples *action selection* (sign of `weighted_score`, handled
          by `determine_action`) from *quality of agreement* (this method).
        - Doesn't reward a small basket with one strongly-conviction outlier;
          weights by share of *total* voting power.
        - HOLD action is meaningless here; return 0.0 (callers should not
          override HOLD confidence — that remains `1 - |score|` to keep
          HOLD's "high confidence we should NOT trade" semantics).

        Args:
            voting_indicators: Dict of voting indicators (excludes GATEKEEPER, VALIDATOR)
            action: Action whose agreement strength to measure (BUY or SELL only)

        Returns:
            Agreement-based confidence in [0, 1]; 0.0 for HOLD / empty.
        """
        if not voting_indicators or action == SignalAction.HOLD:
            return 0.0

        agreeing_weighted_conf = 0.0
        total_weight = 0.0

        for _, indicator in voting_indicators.items():
            weight = self.get_indicator_weight(indicator)
            total_weight += weight
            if indicator.signal == action:
                # Each agreeing indicator contributes weight × its own conviction.
                # Disagreeing indicators contribute 0 to the numerator but still
                # add to the denominator — they dilute confidence.
                agreeing_weighted_conf += weight * float(indicator.confidence)

        if total_weight <= 0:
            return 0.0

        raw_confidence = agreeing_weighted_conf / total_weight
        return validate_confidence(raw_confidence, source="voter.agreement_confidence")

    def filter_non_voting_indicators(
        self, all_indicators: Dict[str, IndicatorSignal]
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

        Included in voting (2025-11-26):
        - Standard: RSI, MACD, BOLLINGER_BANDS, SMA, EMA, STOCHASTIC
        - Advanced: RSI_DIVERGENCE, ICHIMOKU, SQZMOM_ENHANCED
        """
        voting_indicators = {
            k: v
            for k, v in all_indicators.items()
            if k not in ["TREND_FILTER", "VOLUME_CONFIRMATION"]
        }

        # Count weighted indicators
        weighted_count = sum(
            1
            for v in voting_indicators.values()
            if v.metadata and v.metadata.get("weight", 1.0) > 1.0
        )

        logger.info(
            f"Filtered voting indicators: {len(voting_indicators)}/{len(all_indicators)}"
        )
        logger.info(f"  Standard indicators: {len(voting_indicators) - weighted_count}")
        logger.info(f"  Weighted indicators: {weighted_count}")
        logger.debug(f"Voting: {list(voting_indicators.keys())}")
        logger.debug(
            f"Non-voting: {[k for k in all_indicators.keys() if k not in voting_indicators]}"
        )

        return voting_indicators

    def get_voting_summary(self, voting_indicators: Dict[str, IndicatorSignal]) -> Dict:
        """
        Get a detailed summary of the voting indicators

        Args:
            voting_indicators: Dictionary of voting indicators

        Returns:
            Dictionary with voting summary statistics
        """
        standard_indicators = []
        weighted_indicators = []
        total_weight = 0.0

        for name, indicator in voting_indicators.items():
            weight = self.get_indicator_weight(indicator)
            total_weight += weight

            info = {
                "name": name,
                "signal": indicator.signal.value,
                "confidence": indicator.confidence,
                "weight": weight,
                "role": indicator.metadata.get("role", "VOTER")
                if indicator.metadata
                else "VOTER",
            }

            if weight > 1.0:
                weighted_indicators.append(info)
            else:
                standard_indicators.append(info)

        return {
            "total_indicators": len(voting_indicators),
            "standard_count": len(standard_indicators),
            "weighted_count": len(weighted_indicators),
            "total_weight": total_weight,
            "standard_indicators": standard_indicators,
            "weighted_indicators": weighted_indicators,
        }

    # ==================== RESEARCH-BACKED CATEGORY CONSENSUS (2025-11-29) ====================

    def get_indicator_category(self, indicator_name: str) -> str:
        """
        Get the category for an indicator

        Research shows indicators in the same category measure similar things.
        Using multiple from same category gives redundant confirmation.

        Args:
            indicator_name: Name of the indicator

        Returns:
            Category name or "OTHER" if not categorized
        """
        for category, indicators in INDICATOR_CATEGORIES.items():
            if indicator_name in indicators:
                return category
        return "OTHER"

    def calculate_category_consensus(
        self, voting_indicators: Dict[str, IndicatorSignal], target_action: SignalAction
    ) -> Tuple[int, Set[str], Dict[str, list]]:
        """
        Calculate consensus by category (research-backed)

        Instead of just counting indicators, we count how many CATEGORIES
        agree with the signal. This prevents redundant confirmation.

        Example: RSI=BUY, MACD=BUY, STOCHASTIC=BUY = 1 category (MOMENTUM)
                 RSI=BUY, EMA=BUY, BOLLINGER=BUY = 3 categories

        Args:
            voting_indicators: Dictionary of voting indicators
            target_action: The action we're checking consensus for (BUY/SELL)

        Returns:
            Tuple of (category_count, agreeing_categories, category_details)
        """
        category_votes: Dict[str, list] = {
            "MOMENTUM": [],
            "TREND": [],
            "VOLATILITY": [],
            "OTHER": [],
        }

        # Group indicators by category and record their votes
        for name, indicator in voting_indicators.items():
            category = self.get_indicator_category(name)
            vote_info = {
                "name": name,
                "signal": indicator.signal.value,
                "confidence": indicator.confidence,
                "agrees": indicator.signal == target_action,
            }
            category_votes[category].append(vote_info)

        # Count categories that have at least one agreeing indicator
        agreeing_categories: Set[str] = set()
        for category, votes in category_votes.items():
            if any(v["agrees"] for v in votes):
                agreeing_categories.add(category)

        category_count = len(agreeing_categories)

        logger.debug(f"Category consensus for {target_action.value}:")
        for category, votes in category_votes.items():
            if votes:
                agreeing = [v["name"] for v in votes if v["agrees"]]
                logger.debug(
                    f"  {category}: {len(agreeing)}/{len(votes)} agree - {agreeing}"
                )

        return category_count, agreeing_categories, category_votes

    def check_category_diversity(
        self,
        voting_indicators: Dict[str, IndicatorSignal],
        action: SignalAction,
        min_categories: int = 2,
    ) -> Tuple[bool, int, str]:
        """
        Check if signal has sufficient category diversity

        Research shows optimal signals have confirmation from multiple
        indicator categories (momentum + trend + volatility), not just
        multiple indicators from the same category.

        Args:
            voting_indicators: Dictionary of voting indicators
            action: The proposed action (BUY/SELL)
            min_categories: Minimum categories required (default: 2)

        Returns:
            Tuple of (passes, category_count, reason)
        """
        if action == SignalAction.HOLD:
            return True, 0, "HOLD signals don't require category diversity"

        category_count, agreeing_categories, _ = self.calculate_category_consensus(
            voting_indicators, action
        )

        passes = category_count >= min_categories

        if passes:
            reason = f"Category diversity OK: {category_count} categories agree ({', '.join(agreeing_categories)})"
        else:
            reason = f"Insufficient diversity: {category_count}/{min_categories} categories (need {min_categories})"

        logger.info(f"Category diversity check: {reason}")

        return passes, category_count, reason

    def get_research_weight(self, indicator_name: str) -> float:
        """
        Get research-backed weight for an indicator

        Weights based on backtested performance data:
        - SQZMOM_ENHANCED: 1.5x (92% win rate in research)
        - RSI_DIVERGENCE: 1.3x (strong reversal detection)
        - ICHIMOKU: 1.2x (multi-factor confirmation)

        Args:
            indicator_name: Name of the indicator

        Returns:
            Weight multiplier (0.8-1.5x based on research)
        """
        return RESEARCH_WEIGHTS.get(indicator_name, 1.0)
