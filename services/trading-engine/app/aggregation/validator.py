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
    VALIDATOR: Filters low-volume signals

    Responsibilities:
    - Analyzes volume from VOLUME_CONFIRMATION indicator
    - Applies confidence penalty for unconfirmed volume
    - Tracks validation statistics

    Phase 1 Integration:
    - Applied AFTER gatekeeper but BEFORE final decision
    - Does NOT block signals, only reduces confidence
    - 30% confidence penalty for low volume

    Penalty Logic:
    - Confirmed volume → 1.0x (no penalty)
    - Unconfirmed volume → 0.3x (70% penalty)
    """

    def __init__(self):
        """Initialize volume validator"""
        self.confirmed_count = 0
        self.rejected_count = 0
        logger.info("VolumeValidator initialized")

    def validate_volume(
        self,
        confidence: float,
        volume_conf: Optional[IndicatorSignal]
    ) -> Tuple[float, float, str]:
        """
        Validate volume and apply confidence penalty if needed

        Args:
            confidence: Current signal confidence (0.0-1.0)
            volume_conf: VOLUME_CONFIRMATION indicator signal

        Returns:
            Tuple of (modified_confidence, penalty_multiplier, reason)

        Logic:
        - Confirmed volume → confidence * 1.0 (no change)
        - Unconfirmed volume → confidence * 0.3 (reduce to 30%)
        - No volume data → confidence * 1.0 (proceed without check)
        """
        volume_penalty = 1.0  # Multiplier for confidence (1.0 = no penalty)
        volume_reason = ""

        # If no volume confirmation available, pass through unchanged
        if not volume_conf:
            logger.warning("⚠️  Volume Confirmation not available - proceeding without volume check")
            return confidence, volume_penalty, "No volume data"

        # Extract volume confirmation status from metadata
        confirmed = volume_conf.metadata.get("confirmed", False)
        strength = volume_conf.metadata.get("strength", "UNKNOWN")

        if not confirmed:
            # Low volume detected - apply penalty
            volume_penalty = 0.3  # Reduce confidence to 30%
            volume_reason = f"Low volume ({strength})"
            modified_confidence = confidence * volume_penalty
            logger.warning(f"⚠️  Volume NOT confirmed: {strength} - Confidence reduced from {confidence:.2f} to {modified_confidence:.2f}")
            self.rejected_count += 1
        else:
            # Volume confirmed - no penalty
            modified_confidence = confidence
            volume_reason = f"Volume confirmed ({strength})"
            logger.info(f"✅ Volume confirmed: {strength}")
            self.confirmed_count += 1

        return modified_confidence, volume_penalty, volume_reason

    def get_stats(self) -> Dict[str, any]:
        """Get validator statistics"""
        total = self.confirmed_count + self.rejected_count
        return {
            "confirmed": self.confirmed_count,
            "rejected": self.rejected_count,
            "total": total,
            "rejection_rate": (
                self.rejected_count / total if total > 0 else 0.0
            ),
            "confirmation_rate": (
                self.confirmed_count / total if total > 0 else 0.0
            )
        }

    def reset_stats(self):
        """Reset statistics counters"""
        self.confirmed_count = 0
        self.rejected_count = 0
        logger.info("Validator stats reset")
