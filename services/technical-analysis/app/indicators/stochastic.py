"""
Stochastic Oscillator Indicator
Momentum indicator comparing closing price to price range over time
"""

from typing import Dict, List
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class Stochastic:
    """
    Stochastic Oscillator (%K, %D)

    Formula:
    %K = 100 × (Close - Lowest Low) / (Highest High - Lowest Low)
    %D = SMA(%K, smooth_period)

    Signals:
    - Overbought: %K > 80 (potential reversal down)
    - Oversold: %K < 20 (potential reversal up)
    - Bullish: %K crosses above %D
    - Bearish: %K crosses below %D
    """

    def __init__(
        self,
        period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3,
        overbought: int = 80,
        oversold: int = 20
    ):
        self.period = period
        self.smooth_k = smooth_k
        self.smooth_d = smooth_d
        self.overbought = overbought
        self.oversold = oversold

    def calculate(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Dict:
        """
        Calculate Stochastic Oscillator

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices

        Returns:
            {
                'k': float,  # %K value (0-100)
                'd': float,  # %D value (0-100)
                'signal': 'BUY' | 'SELL' | 'HOLD',
                'condition': 'OVERBOUGHT' | 'OVERSOLD' | 'NEUTRAL',
                'confidence': float,
                'crossover': 'BULLISH' | 'BEARISH' | 'NONE',
                'description': str,
                'timestamp': int
            }
        """

        if len(highs) < self.period + self.smooth_k or len(lows) < self.period + self.smooth_k or len(closes) < self.period + self.smooth_k:
            logger.warning(f"Insufficient data for Stochastic: need {self.period + self.smooth_k} candles")
            return self._neutral_response()

        try:
            df = pd.DataFrame({
                'high': highs,
                'low': lows,
                'close': closes
            })

            # Calculate %K
            # Lowest low and highest high over period
            df['lowest_low'] = df['low'].rolling(window=self.period).min()
            df['highest_high'] = df['high'].rolling(window=self.period).max()

            # Fixed: Calculate raw %K with division by zero protection (Critical Issue #3)
            # When highest_high == lowest_low (flat market), division would crash
            # Replace 0 range with inf to avoid division by zero
            price_range = (df['highest_high'] - df['lowest_low']).replace(0, np.inf)
            df['k_raw'] = 100 * (df['close'] - df['lowest_low']) / price_range

            # Smooth %K
            df['k'] = df['k_raw'].rolling(window=self.smooth_k).mean()

            # %D = SMA of %K
            df['d'] = df['k'].rolling(window=self.smooth_d).mean()

            # Get current and previous values
            k_current = df['k'].iloc[-1]
            d_current = df['d'].iloc[-1]
            k_prev = df['k'].iloc[-2] if len(df) > 1 else k_current
            d_prev = df['d'].iloc[-2] if len(df) > 1 else d_current

            # Determine condition
            if k_current > self.overbought:
                condition = "OVERBOUGHT"
            elif k_current < self.oversold:
                condition = "OVERSOLD"
            else:
                condition = "NEUTRAL"

            # Detect crossover
            bullish_cross = k_prev <= d_prev and k_current > d_current
            bearish_cross = k_prev >= d_prev and k_current < d_current

            if bullish_cross:
                crossover = "BULLISH"
            elif bearish_cross:
                crossover = "BEARISH"
            else:
                crossover = "NONE"

            # Generate signal
            if condition == "OVERSOLD" and (crossover == "BULLISH" or k_current > d_current):
                signal = "BUY"
                confidence = 0.9  # High confidence in oversold + bullish
            elif condition == "OVERBOUGHT" and (crossover == "BEARISH" or k_current < d_current):
                signal = "SELL"
                confidence = 0.9
            elif crossover == "BULLISH":
                signal = "BUY"
                confidence = 0.6  # Moderate confidence on crossover only
            elif crossover == "BEARISH":
                signal = "SELL"
                confidence = 0.6
            else:
                signal = "HOLD"
                confidence = 0.3

            # Description
            description = f"{condition}"
            if crossover != "NONE":
                description += f", {crossover} crossover"
            description += f" (K={k_current:.1f}, D={d_current:.1f})"

            return {
                "k": float(k_current),
                "d": float(d_current),
                "signal": signal,
                "condition": condition,
                "confidence": float(confidence),
                "crossover": crossover,
                "description": description,
                "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
            }

        except Exception as e:
            logger.error(f"Error calculating Stochastic: {e}")
            return self._neutral_response()

    def _neutral_response(self) -> Dict:
        """Return neutral response when calculation fails"""
        return {
            "k": 50.0,
            "d": 50.0,
            "signal": "HOLD",
            "condition": "NEUTRAL",
            "confidence": 0.0,
            "crossover": "NONE",
            "description": "Insufficient data or error",
            "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
        }
