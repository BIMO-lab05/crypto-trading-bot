"""
Volume Validator Module
Purpose: Filters signals based on volume confirmation
Pattern: Strangler Fig - Extracted from signal_aggregator.py
"""

import logging
from typing import Dict, Optional, Tuple
from app.models import IndicatorSignal

logger = logging.getLogger(__name__)


class VolumeValidator:
    """
    VALIDATOR: Filters low-volume signals with adaptive weighting

    Responsibilities:
    - Analyzes volume from VOLUME_CONFIRMATION indicator
    - Applies graduated confidence penalties based on volume strength
    - Tracks validation statistics per strength level

    Phase 2 Enhancement (Adaptive Weighting):
    - Applied AFTER gatekeeper but BEFORE final decision
    - Does NOT block signals, only reduces confidence
    - Graduated penalties based on volume strength

    Adaptive Penalty Logic:
    - CONFIRMED + STRONG:      1.0x (no penalty)
    - CONFIRMED + MODERATE:    0.9x (10% penalty)
    - NOT CONFIRMED + MODERATE: 0.7x (30% penalty)
    - NOT CONFIRMED + WEAK:     0.5x (50% penalty)
    - NOT CONFIRMED + MINIMAL:  0.3x (70% penalty)
    - UNKNOWN:                  0.8x (20% penalty - safety fallback)
    """

    def __init__(self):
        """Initialize volume validator with adaptive weighting"""
        self.confirmed_count = 0
        self.rejected_count = 0

        # Track statistics per volume strength level
        self.strength_stats = {
            "STRONG": 0,
            "MODERATE": 0,
            "WEAK": 0,
            "MINIMAL": 0,
            "UNKNOWN": 0
        }

        logger.info("VolumeValidator initialized with adaptive weighting")

    def validate_volume(
        self,
        confidence: float,
        volume_conf: Optional[IndicatorSignal]
    ) -> Tuple[float, float, str]:
        """
        Validate volume and apply adaptive confidence penalty

        Args:
            confidence: Current signal confidence (0.0-1.0)
            volume_conf: VOLUME_CONFIRMATION indicator signal

        Returns:
            Tuple of (modified_confidence, penalty_multiplier, reason)

        Adaptive Logic (Phase 2):
        - CONFIRMED + STRONG:      1.0x (no penalty)
        - CONFIRMED + MODERATE:    0.9x (10% penalty)
        - NOT CONFIRMED + MODERATE: 0.7x (30% penalty)
        - NOT CONFIRMED + WEAK:     0.5x (50% penalty)
        - NOT CONFIRMED + MINIMAL:  0.3x (70% penalty)
        - UNKNOWN:                  0.8x (20% penalty)
        - No volume data:           1.0x (pass through)
        """
        volume_penalty = 1.0  # Default: no penalty
        volume_reason = ""

        # If no volume confirmation available, pass through unchanged
        if not volume_conf:
            logger.warning("⚠️  Volume Confirmation not available - proceeding without volume check")
            return confidence, volume_penalty, "No volume data"

        # Extract volume confirmation status and strength from metadata
        confirmed = volume_conf.metadata.get("confirmed", False)
        strength = volume_conf.metadata.get("strength", "UNKNOWN").upper()

        # Track strength statistics
        if strength in self.strength_stats:
            self.strength_stats[strength] += 1

        # Apply adaptive penalty based on confirmation status AND strength
        if confirmed:
            # Volume is confirmed - apply minimal or no penalty
            if strength == "STRONG":
                volume_penalty = 1.0  # No penalty
                volume_reason = "Strong volume confirmed"
                logger.info(f"✅ Volume STRONG: {strength} - No penalty (1.0x)")
                self.confirmed_count += 1

            elif strength == "MODERATE":
                volume_penalty = 0.9  # Minor penalty (10%)
                volume_reason = "Moderate volume confirmed"
                logger.info(f"✓ Volume MODERATE: {strength} - Minor penalty (0.9x)")
                self.confirmed_count += 1

            else:
                # Confirmed but unknown strength - conservative approach
                volume_penalty = 0.9
                volume_reason = f"Volume confirmed ({strength})"
                logger.info(f"✓ Volume confirmed: {strength} - Conservative penalty (0.9x)")
                self.confirmed_count += 1

        else:
            # Volume is NOT confirmed - apply graduated penalties
            if strength == "MODERATE":
                # PROFITABILITY FIX 2025-11-27: Reduced from 0.7x to 0.8x (20% penalty)
                # - Combined with gatekeeper, this allows moderate-quality signals through
                volume_penalty = 0.8  # 20% penalty
                volume_reason = "Moderate volume (unconfirmed)"
                logger.warning(f"⚠️  Volume MODERATE (unconfirmed) - Penalty: 0.8x")
                self.rejected_count += 1

            elif strength == "WEAK":
                # PROFITABILITY FIX 2025-11-27: Reduced from 0.6x to 0.75x (25% penalty)
                # - 40% penalty combined with gatekeeper 15% = 49% total reduction
                # - This was rejecting 100% of signals, bot executed 0 trades
                # - 25% penalty allows quality signals while still filtering noise
                # - Combined penalty now: 0.85 * 0.75 = 0.6375x (was 0.45x)
                volume_penalty = 0.75  # 25% penalty
                volume_reason = "Weak volume"
                logger.warning(f"⚠️  Volume WEAK - Penalty: 0.75x")
                self.rejected_count += 1

            elif strength == "MINIMAL":
                # PROFITABILITY FIX 2025-11-27: Reduced from 0.3x to 0.5x (50% penalty)
                # - 70% penalty was too harsh, combined with gatekeeper = nearly 100% filter
                # - 50% penalty still penalizes low-volume signals but allows some trades
                volume_penalty = 0.5  # 50% penalty
                volume_reason = "Minimal volume"
                logger.warning(f"⚠️  Volume MINIMAL - Penalty: 0.5x")
                self.rejected_count += 1

            else:
                # Unknown strength - use minimal penalty (AGGRESSIVE 2025-11-28)
                # Changed from 0.8x to 0.95x to allow more trades
                volume_penalty = 0.95  # 5% penalty only
                volume_reason = f"Unknown volume strength ({strength})"
                logger.warning(f"⚠️  Volume UNKNOWN: {strength} - Minimal penalty: 0.95x")
                self.rejected_count += 1

        # Calculate modified confidence
        modified_confidence = confidence * volume_penalty

        # Log the confidence adjustment
        if volume_penalty < 1.0:
            logger.info(f"  📉 Confidence adjusted: {confidence:.2f} → {modified_confidence:.2f} (×{volume_penalty:.1f})")
        else:
            logger.info(f"  ✓ Confidence maintained: {confidence:.2f} (no penalty)")

        return modified_confidence, volume_penalty, volume_reason

    def get_stats(self) -> Dict[str, any]:
        """
        Get validator statistics including adaptive weighting breakdown

        Returns:
            Dict with confirmation/rejection stats and strength distribution
        """
        total = self.confirmed_count + self.rejected_count
        total_strength = sum(self.strength_stats.values())

        return {
            "confirmed": self.confirmed_count,
            "rejected": self.rejected_count,
            "total": total,
            "rejection_rate": (
                self.rejected_count / total if total > 0 else 0.0
            ),
            "confirmation_rate": (
                self.confirmed_count / total if total > 0 else 0.0
            ),
            # Adaptive weighting breakdown
            "strength_distribution": {
                strength: {
                    "count": count,
                    "percentage": (count / total_strength * 100) if total_strength > 0 else 0.0
                }
                for strength, count in self.strength_stats.items()
            },
            "average_penalty_estimate": self._calculate_average_penalty()
        }

    def _calculate_average_penalty(self) -> float:
        """
        Calculate average penalty multiplier based on strength distribution

        Returns:
            Estimated average penalty (0.0 to 1.0)
        """
        total = sum(self.strength_stats.values())
        if total == 0:
            return 1.0

        # Weight penalties by frequency
        penalty_weights = {
            "STRONG": 1.0,
            "MODERATE": 0.9,  # Assumed average between confirmed (0.9) and unconfirmed (0.7)
            "WEAK": 0.5,
            "MINIMAL": 0.3,
            "UNKNOWN": 0.8
        }

        weighted_sum = sum(
            self.strength_stats[strength] * penalty_weights.get(strength, 0.8)
            for strength in self.strength_stats.keys()
        )

        return weighted_sum / total

    def reset_stats(self):
        """Reset all statistics counters including strength distribution"""
        self.confirmed_count = 0
        self.rejected_count = 0

        # Reset strength statistics
        for strength in self.strength_stats:
            self.strength_stats[strength] = 0

        logger.info("Validator stats reset (including strength distribution)")
