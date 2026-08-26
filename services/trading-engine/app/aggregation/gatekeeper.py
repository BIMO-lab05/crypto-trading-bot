"""
Trend Gatekeeper Module
Purpose: Blocks counter-trend trades using Trend Filter indicator
Pattern: Strangler Fig - Extracted from signal_aggregator.py
"""

import logging
from typing import Dict, Optional, Tuple

from app.config import get_settings
from app.models import IndicatorSignal, SignalAction

logger = logging.getLogger(__name__)


class TrendGatekeeper:
    """
    GATEKEEPER: Filters counter-trend trades (relaxed version for more trading)

    Responsibilities:
    - Analyzes trend direction from TREND_FILTER indicator
    - Applies penalties to counter-trend signals (instead of blocking)
    - Reduces confidence in NEUTRAL trends

    ADJUSTED FOR MORE AGGRESSIVE TRADING (2025-11-26):
    - Counter-trend trades are penalized but NOT fully blocked
    - Allows more trading in ranging/neutral markets
    - Reduced penalties across the board

    2026-08-21: thresholds moved to Settings. This docstring previously said
    the blocking threshold was 0.9 while the code applied 0.95 — a reader
    could not tell which was live. The value now comes from
    `settings.gatekeeper_block_threshold` and is reported through the signal
    funnel alongside the TREND_FILTER confidence it was compared against.
    """

    def __init__(self):
        """Initialize trend gatekeeper"""
        self.blocked_count = 0
        self.passed_count = 0
        self.penalized_count = 0
        settings = get_settings()
        self.block_threshold = float(settings.gatekeeper_block_threshold)
        self.block_penalty = float(settings.gatekeeper_block_penalty)
        self.counter_trend_penalty = float(
            settings.gatekeeper_counter_trend_penalty
        )
        logger.info(
            "TrendGatekeeper initialized: block_threshold=%.2f "
            "block_penalty=%.2f counter_trend_penalty=%.2f",
            self.block_threshold,
            self.block_penalty,
            self.counter_trend_penalty,
        )

    def check_signal(
        self,
        action: SignalAction,
        confidence: float,
        trend_filter: Optional[IndicatorSignal]
    ) -> Tuple[SignalAction, float, bool, str]:
        """
        Check if signal should be penalized by trend filter

        Args:
            action: Preliminary trading action (BUY/SELL/HOLD)
            confidence: Signal confidence (0.0-1.0)
            trend_filter: TREND_FILTER indicator signal

        Returns:
            Tuple of (modified_action, modified_confidence, blocked, reason)

        RELAXED Logic (more aggressive trading - 2025-11-26):
        - BUY + BEARISH trend + very high trend confidence (>=0.9) -> BLOCK
        - BUY + BEARISH trend + lower trend confidence -> PENALIZE (0.6x instead of 0.5x)
        - SELL + BULLISH trend + very high trend confidence (>=0.9) -> BLOCK
        - SELL + BULLISH trend + lower trend confidence -> PENALIZE (0.6x instead of 0.5x)
        - Any + NEUTRAL trend -> ALLOW with minimal penalty (0.9x instead of 0.85x)
        - Any + matching trend -> ALLOW unchanged
        - HOLD signals -> ALLOW unchanged (no need to filter)
        """
        # If no trend filter available, pass through unchanged
        if not trend_filter:
            logger.warning("Trend Filter not available - proceeding without trend check")
            return action, confidence, False, "No trend filter"

        # HOLD signals don't need filtering
        if action == SignalAction.HOLD:
            return action, confidence, False, "HOLD signal"

        # Extract trend from indicator metadata
        trend = trend_filter.metadata.get("trend")
        trend_confidence = trend_filter.confidence
        logger.info(f"Trend Filter: {trend} (confidence: {trend_confidence:.2f})")

        trend_blocked = False
        trend_reason = ""
        modified_action = action
        modified_confidence = confidence

        # Check for counter-trend trades
        if action == SignalAction.BUY and trend == "BEARISH":
            # Counter-trend BUY in BEARISH
            # AGGRESSIVE 2025-11-28: Only block at extreme confidence (>=0.95)
            # - Changed from 0.75 to allow more counter-trend reversal trades
            if trend_confidence >= self.block_threshold:
                # Extremely strong bearish trend - block the trade
                trend_blocked = True
                trend_reason = (
                    f"Counter-trend blocked (BUY in extreme BEARISH): "
                    f"trend_confidence {trend_confidence:.4f} >= "
                    f"{self.block_threshold:.2f}"
                )
                modified_action = SignalAction.HOLD
                modified_confidence *= self.block_penalty
                logger.warning(f"BLOCKED: {trend_reason}")
                self.blocked_count += 1
            else:
                # Bearish trend - minimal penalty to allow reversal trades
                trend_blocked = False
                trend_reason = "Counter-trend penalty (BUY in BEARISH)"
                # AGGRESSIVE 2025-11-28: Reduced from 0.85x to 0.95x (5% penalty)
                modified_confidence *= self.counter_trend_penalty
                logger.info(f"PENALIZED: {trend_reason}")
                self.penalized_count += 1

        elif action == SignalAction.SELL and trend == "BULLISH":
            # Counter-trend SELL in BULLISH
            # AGGRESSIVE 2025-11-28: Only block at extreme confidence (>=0.95)
            if trend_confidence >= self.block_threshold:
                # Extremely strong bullish trend - block the trade
                trend_blocked = True
                trend_reason = (
                    f"Counter-trend blocked (SELL in extreme BULLISH): "
                    f"trend_confidence {trend_confidence:.4f} >= "
                    f"{self.block_threshold:.2f}"
                )
                modified_action = SignalAction.HOLD
                modified_confidence *= self.block_penalty
                logger.warning(f"BLOCKED: {trend_reason}")
                self.blocked_count += 1
            else:
                # Bullish trend - minimal penalty to allow reversal trades
                trend_blocked = False
                trend_reason = "Counter-trend penalty (SELL in BULLISH)"
                # AGGRESSIVE 2025-11-28: Reduced from 0.85x to 0.95x (5% penalty)
                modified_confidence *= self.counter_trend_penalty
                logger.info(f"PENALIZED: {trend_reason}")
                self.penalized_count += 1

        elif trend == "NEUTRAL":
            # Neutral trend: allow with no penalty
            # AGGRESSIVE 2025-11-28: Removed penalty for neutral trends
            modified_confidence *= 1.0  # No penalty
            trend_reason = "Neutral trend (no penalty)"
            logger.info(f"NEUTRAL: {trend_reason}")
            self.passed_count += 1

        else:
            # Trend aligns with signal - pass through
            trend_reason = f"{action.value} aligned with {trend} trend"
            logger.info(f"PASSED: {trend_reason}")
            self.passed_count += 1

        return modified_action, modified_confidence, trend_blocked, trend_reason

    def get_stats(self) -> Dict[str, any]:
        """Get gatekeeper statistics"""
        total = self.blocked_count + self.passed_count + self.penalized_count
        return {
            "blocked": self.blocked_count,
            "passed": self.passed_count,
            "penalized": self.penalized_count,
            "total": total,
            "block_rate": (
                self.blocked_count / total if total > 0 else 0.0
            ),
            "penalty_rate": (
                self.penalized_count / total if total > 0 else 0.0
            )
        }

    def reset_stats(self):
        """Reset statistics counters"""
        self.blocked_count = 0
        self.passed_count = 0
        self.penalized_count = 0
        logger.info("Gatekeeper stats reset")
