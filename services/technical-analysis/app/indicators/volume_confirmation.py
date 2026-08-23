"""
Volume Confirmation Indicator
Validates signals based on trading volume
Prevents false breakouts on low volume
"""

from typing import Dict, List
import pandas as pd
import numpy as np
import logging
logger = logging.getLogger(__name__)


class VolumeConfirmation:
    """
    Volume-based signal confirmation

    Logic:
    - High volume (>1.5x avg): Strong confirmation
    - Medium volume (1.2-1.5x avg): Moderate confirmation
    - Normal volume (1.0-1.2x avg): Weak confirmation
    - Low volume (<1.0x avg): Rejection
    """

    def __init__(
        self,
        period: int = 20,
        breakout_threshold: float = 1.2,
        strong_threshold: float = 1.5
    ):
        self.period = period
        self.breakout_threshold = breakout_threshold
        self.strong_threshold = strong_threshold

    def calculate(
        self,
        volumes: List[float],
        signal_type: str = "breakout"  # "breakout" or "continuation"
    ) -> Dict:
        """
        Calculate volume confirmation

        Args:
            volumes: List of volume values (oldest to newest)
            signal_type: "breakout" requires higher volume, "continuation" is more lenient

        Returns:
            {
                'confirmed': bool,
                'current_volume': float,
                'avg_volume': float,
                'volume_ratio': float,
                'confidence': float,
                'strength': 'STRONG' | 'MODERATE' | 'WEAK' | 'INSUFFICIENT',
                'signal': 'CONFIRM' | 'REJECT',
                'timestamp': int
            }
        """

        if len(volumes) < self.period:
            logger.warning(f"Insufficient volume data: {len(volumes)} < {self.period}")
            return self._reject_response()

        try:
            # Current volume and average
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-self.period:])

            # Volume ratio
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            # Confirmation threshold depends on what the caller is asking about:
            # a breakout wants volume expansion (>= breakout_threshold), a
            # continuation only wants volume at or above its own average.
            #
            # 2026-08-23: this local was computed and never read. The WEAK branch
            # below tested `signal_type == "continuation"` directly, so the
            # breakout/continuation switch existed in name only. Wiring it in is
            # behaviour-identical for both callers -- inside the WEAK branch
            # `volume_ratio >= 1.0` holds by construction, and for breakout the
            # band 1.0-1.2 stays unconfirmed -- but it removes the dead variable
            # and makes the rule one expression instead of two that must agree.
            #
            # NOTE: the trading engine only ever requests signal_type="breakout"
            # (app/signal_aggregator.py builds the URL with &signal_type=breakout),
            # so the WEAK band is still unconfirmable in the live path. Making it
            # reachable there means changing what the engine asks for, which is a
            # behaviour change and is deliberately NOT made here.
            threshold = self.breakout_threshold if signal_type == "breakout" else 1.0

            # Classify volume strength
            if volume_ratio >= self.strong_threshold:
                strength = "STRONG"
                confidence = 1.0
                confirmed = True
            elif volume_ratio >= self.breakout_threshold:
                strength = "MODERATE"
                confidence = 0.7
                confirmed = True
            elif volume_ratio >= 1.0:
                strength = "WEAK"
                confidence = 0.4
                # bool() is load-bearing: volume_ratio is a numpy float, so the
                # comparison yields numpy.bool_, which fails `is False` and does
                # not JSON-serialise. The branch it replaced returned a Python
                # bool, so dropping this would be a silent type regression.
                confirmed = bool(volume_ratio >= threshold)
            else:
                strength = "INSUFFICIENT"
                confidence = 0.1
                confirmed = False

            return {
                "confirmed": confirmed,
                "current_volume": float(current_volume),
                "avg_volume": float(avg_volume),
                "volume_ratio": float(volume_ratio),
                "confidence": float(confidence),
                "strength": strength,
                "signal": "CONFIRM" if confirmed else "REJECT",
                "description": f"{strength} volume ({volume_ratio:.2f}x average)",
                "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
            }

        except Exception as e:
            logger.error(f"Error calculating volume confirmation: {e}")
            return self._reject_response()

    def _reject_response(self) -> Dict:
        """Return rejection response when calculation fails"""
        return {
            "confirmed": False,
            "current_volume": 0.0,
            "avg_volume": 0.0,
            "volume_ratio": 0.0,
            "confidence": 0.0,
            "strength": "INSUFFICIENT",
            "signal": "REJECT",
            "description": "Insufficient data or error",
            "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
        }
