"""
Trend Filter Indicator
Uses 50 EMA and 200 EMA to determine market trend direction
Prevents counter-trend trading
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging
logger = logging.getLogger(__name__)


class TrendFilter:
    """
    Trend filter using dual EMA system

    Logic:
    - Bullish: 50 EMA > 200 EMA + spread > 0.5%
    - Bearish: 50 EMA < 200 EMA + spread > 0.5%
    - Neutral: EMAs within 0.5% (choppy market)

    Purpose: Only allow trades in the direction of the major trend
    """

    def __init__(
        self,
        fast_period: int = 50,
        slow_period: int = 200,
        neutral_threshold: float = 0.005  # 0.5% threshold
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.neutral_threshold = neutral_threshold

    def calculate(self, prices: List[float]) -> Dict:
        """
        Calculate trend filter signal

        Args:
            prices: List of closing prices (oldest to newest)

        Returns:
            {
                'trend': 'BULLISH' | 'BEARISH' | 'NEUTRAL',
                'fast_ema': float,
                'slow_ema': float,
                'spread_pct': float,
                'confidence': float,  # 0.0 to 1.0
                'signal': 'BUY' | 'SELL' | 'HOLD',
                'timestamp': int
            }
        """

        if len(prices) < self.slow_period:
            logger.warning(f"Insufficient data for trend filter: {len(prices)} < {self.slow_period}")
            return self._neutral_response()

        try:
            # Convert to pandas Series for EMA calculation
            price_series = pd.Series(prices)

            # Calculate EMAs
            fast_ema = price_series.ewm(span=self.fast_period, adjust=False).mean().iloc[-1]
            slow_ema = price_series.ewm(span=self.slow_period, adjust=False).mean().iloc[-1]

            # Calculate spread percentage
            spread_pct = (fast_ema - slow_ema) / slow_ema

            # Determine trend
            if spread_pct > self.neutral_threshold:
                trend = "BULLISH"
                signal = "BUY"
                # Confidence based on spread magnitude (capped at 1.0)
                confidence = min(abs(spread_pct) / 0.05, 1.0)  # 5% spread = 100% confidence
            elif spread_pct < -self.neutral_threshold:
                trend = "BEARISH"
                signal = "SELL"
                confidence = min(abs(spread_pct) / 0.05, 1.0)
            else:
                trend = "NEUTRAL"
                signal = "HOLD"
                confidence = 0.3  # Low confidence in choppy markets

            return {
                "trend": trend,
                "fast_ema": float(fast_ema),
                "slow_ema": float(slow_ema),
                "spread_pct": float(spread_pct),
                "confidence": float(confidence),
                "signal": signal,
                "description": f"{trend} trend ({spread_pct*100:.2f}% spread)",
                "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
            }

        except Exception as e:
            logger.error(f"Error calculating trend filter: {e}")
            return self._neutral_response()

    def _neutral_response(self) -> Dict:
        """Return neutral response when calculation fails"""
        return {
            "trend": "NEUTRAL",
            "fast_ema": 0.0,
            "slow_ema": 0.0,
            "spread_pct": 0.0,
            "confidence": 0.0,
            "signal": "HOLD",
            "description": "Insufficient data or error",
            "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
        }
