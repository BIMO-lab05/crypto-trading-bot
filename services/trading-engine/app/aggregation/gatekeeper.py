"""
Trend Gatekeeper Module
Purpose: Blocks counter-trend trades using Trend Filter indicator
Pattern: Strangler Fig - Extracted from signal_aggregator.py
"""

import logging
from typing import Dict, Optional, Tuple
from app.models import IndicatorSignal, SignalAction

logger = logging.getLogger(__name__)


class TrendGatekeeper:
    """
    GATEKEEPER: Blocks counter-trend trades

    Responsibilities:
    - Analyzes trend direction from TREND_FILTER indicator
    - Blocks BUY signals in BEARISH trends
    - Blocks SELL signals in BULLISH trends
    - Reduces confidence in NEUTRAL trends

    Phase 1 Integration:
    - Applied BEFORE voting aggregation
    - Can completely block a signal
    - Works in conjunction with VolumeValidator
    """

    def __init__(self):
        """Initialize trend gatekeeper"""
        self.blocked_count = 0
        self.passed_count = 0
        logger.info("TrendGatekeeper initialized")

    def check_signal(
        self,
        action: SignalAction,
        confidence: float,
        trend_filter: Optional[IndicatorSignal]
    ) -> Tuple[SignalAction, float, bool, str]:
        """
        Check if signal should be blocked by trend filter

        Args:
            action: Preliminary trading action (BUY/SELL/HOLD)
            confidence: Signal confidence (0.0-1.0)
            trend_filter: TREND_FILTER indicator signal

        Returns:
            Tuple of (modified_action, modified_confidence, blocked, reason)

        Logic:
        - BUY + BEARISH trend → BLOCK (set to HOLD, confidence *= 0.2)
        - SELL + BULLISH trend → BLOCK (set to HOLD, confidence *= 0.2)
        - Any + NEUTRAL trend → ALLOW with reduced confidence (* 0.7)
        - Any + matching trend → ALLOW unchanged
        - HOLD signals → ALLOW unchanged (no need to filter)
        """
        # If no trend filter available, pass through unchanged
        if not trend_filter:
            logger.warning("⚠️  Trend Filter not available - proceeding without trend check")
            return action, confidence, False, "No trend filter"

        # HOLD signals don't need filtering
        if action == SignalAction.HOLD:
            return action, confidence, False, "HOLD signal"

        # Extract trend from indicator metadata
        trend = trend_filter.metadata.get("trend")
        logger.info(f"🔍 Trend Filter: {trend} (confidence: {trend_filter.confidence:.2f})")

        trend_blocked = False
        trend_reason = ""
        modified_action = action
        modified_confidence = confidence

        # Check for counter-trend trades
        if action == SignalAction.BUY and trend == "BEARISH":
            # Block BUY in BEARISH trend
            trend_blocked = True
            trend_reason = "Counter-trend (BUY in BEARISH trend)"
            modified_action = SignalAction.HOLD
            modified_confidence *= 0.2  # Drastically reduce confidence
            logger.warning(f"🚫 BLOCKED: {trend_reason}")
            self.blocked_count += 1

        elif action == SignalAction.SELL and trend == "BULLISH":
            # Block SELL in BULLISH trend
            trend_blocked = True
            trend_reason = "Counter-trend (SELL in BULLISH trend)"
            modified_action = SignalAction.HOLD
            modified_confidence *= 0.2
            logger.warning(f"🚫 BLOCKED: {trend_reason}")
            self.blocked_count += 1

        elif trend == "NEUTRAL":
            # Neutral trend: allow but reduce confidence
            modified_confidence *= 0.7
            trend_reason = "Neutral trend (reduced confidence)"
            logger.info(f"⚠️  {trend_reason}")
            self.passed_count += 1

        else:
            # Trend aligns with signal - pass through
            trend_reason = f"{action.value} aligned with {trend} trend"
            logger.info(f"✅ PASSED: {trend_reason}")
            self.passed_count += 1

        return modified_action, modified_confidence, trend_blocked, trend_reason

    def get_stats(self) -> Dict[str, int]:
        """Get gatekeeper statistics"""
        return {
            "blocked": self.blocked_count,
            "passed": self.passed_count,
            "total": self.blocked_count + self.passed_count,
            "block_rate": (
                self.blocked_count / (self.blocked_count + self.passed_count)
                if (self.blocked_count + self.passed_count) > 0
                else 0.0
            )
        }

    def reset_stats(self):
        """Reset statistics counters"""
        self.blocked_count = 0
        self.passed_count = 0
        logger.info("Gatekeeper stats reset")
