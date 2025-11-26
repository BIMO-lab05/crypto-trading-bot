"""
Bollinger Bands Calculator
Purpose: Calculate Bollinger Bands and generate trading signals

Updated: Widened signal zones to generate more BUY/SELL signals
- Strong BUY zone: 0.1 -> 0.15 (price position)
- Moderate BUY zone: 0.3 -> 0.35
- Strong SELL zone: 0.9 -> 0.85
- Moderate SELL zone: 0.7 -> 0.65
- HOLD zone narrowed: 0.3-0.7 -> 0.35-0.65
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple, Dict
from app.models import SignalType

logger = logging.getLogger(__name__)


class BollingerBandsCalculator:
    """
    Calculate Bollinger Bands

    Bollinger Bands are volatility bands placed above and below
    a moving average. They expand and contract as volatility changes.

    Components:
        - Middle Band = SMA(period)
        - Upper Band = Middle Band + (std_dev x StdDev)
        - Lower Band = Middle Band - (std_dev x StdDev)
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        """
        Initialize Bollinger Bands calculator

        Args:
            period: Number of periods for SMA (default: 20)
            std_dev: Number of standard deviations (default: 2.0)
        """
        self.period = period
        self.std_dev = std_dev
        logger.info(f"Bollinger Bands Calculator initialized: period={period}, std_dev={std_dev}")

    def calculate(self, df: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        Calculate Bollinger Bands

        Args:
            df: DataFrame with 'close' column

        Returns:
            Dict with upper_band, middle_band, lower_band, current_price
            or None if insufficient data
        """
        if len(df) < self.period:
            logger.warning(f"Insufficient data for BB: need {self.period}, got {len(df)}")
            return None

        try:
            # Calculate middle band (SMA)
            middle_band = df['close'].rolling(window=self.period).mean()

            # Calculate standard deviation
            std = df['close'].rolling(window=self.period).std()

            # Calculate upper and lower bands
            upper_band = middle_band + (std * self.std_dev)
            lower_band = middle_band - (std * self.std_dev)

            # Get current price
            current_price = df['close'].iloc[-1]

            # Fixed: Calculate bandwidth with division by zero protection (Critical Issue #2)
            # When middle_band is 0 or very close to 0, bandwidth calculation would crash
            middle_val = middle_band.iloc[-1]
            if middle_val == 0 or np.isnan(middle_val):
                logger.warning(f"Middle band is {middle_val}, cannot calculate bandwidth")
                bandwidth = 0.0
            else:
                bandwidth = float((upper_band.iloc[-1] - lower_band.iloc[-1]) / middle_val)

            result = {
                "upper_band": float(upper_band.iloc[-1]),
                "middle_band": float(middle_val),
                "lower_band": float(lower_band.iloc[-1]),
                "current_price": float(current_price),
                "bandwidth": bandwidth
            }

            logger.debug(f"Calculated BB: {result}")
            return result

        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            return None

    def generate_signal(self, bb_data: Dict[str, float]) -> Tuple[SignalType, float]:
        """
        Generate trading signal based on Bollinger Bands

        Args:
            bb_data: Dict with band values and current price

        Returns:
            Tuple of (SignalType, confidence)

        Signal Logic (Updated for more signals):
            - Price near/below lower band (position <= 0.15) -> Strong BUY
            - Price in lower zone (position <= 0.35) -> Moderate BUY
            - Price near/above upper band (position >= 0.85) -> Strong SELL
            - Price in upper zone (position >= 0.65) -> Moderate SELL
            - Price in middle (0.35-0.65) -> HOLD (narrowed from 0.3-0.7)
        """
        upper = bb_data["upper_band"]
        middle = bb_data["middle_band"]
        lower = bb_data["lower_band"]
        price = bb_data["current_price"]

        # Calculate price position within bands (0 = lower, 0.5 = middle, 1 = upper)
        band_range = upper - lower
        if band_range == 0:
            return SignalType.HOLD, 0.1

        price_position = (price - lower) / band_range

        # Generate signal based on price position
        # Updated: Widened BUY/SELL zones for more signals
        if price_position <= 0.15:
            # Price at or below lower band - Strong BUY
            # Updated: Threshold widened from 0.1 to 0.15
            signal = SignalType.BUY
            confidence = 1.0 - price_position * 4  # Higher confidence at lower band
            logger.info(f"Price {price:.2f} at lower band {lower:.2f} -> Strong BUY (pos: {price_position:.2f})")

        elif price_position <= 0.35:
            # Price in lower zone - Moderate BUY
            # Updated: Threshold widened from 0.3 to 0.35
            signal = SignalType.BUY
            confidence = 0.7 - (price_position - 0.15) * 1.5  # Confidence decreases as price rises
            logger.info(f"Price {price:.2f} in lower zone -> Moderate BUY (pos: {price_position:.2f})")

        elif price_position >= 0.85:
            # Price at or above upper band - Strong SELL
            # Updated: Threshold lowered from 0.9 to 0.85
            signal = SignalType.SELL
            confidence = price_position
            logger.info(f"Price {price:.2f} at upper band {upper:.2f} -> Strong SELL (pos: {price_position:.2f})")

        elif price_position >= 0.65:
            # Price in upper zone - Moderate SELL
            # Updated: Threshold lowered from 0.7 to 0.65
            signal = SignalType.SELL
            confidence = (price_position - 0.65) * 2.5 + 0.4  # Confidence increases as price rises
            logger.info(f"Price {price:.2f} in upper zone -> Moderate SELL (pos: {price_position:.2f})")

        else:
            # Price in middle of bands - HOLD
            # Updated: Narrowed HOLD zone from 0.3-0.7 to 0.35-0.65
            signal = SignalType.HOLD
            # Lower confidence when price is in middle
            confidence = 0.3
            logger.debug(f"Price {price:.2f} in middle of bands (0.35-0.65) -> HOLD")

        # Adjust confidence based on bandwidth (volatility)
        bandwidth = bb_data.get("bandwidth", 0.04)
        if bandwidth < 0.02:
            # Very narrow bands (low volatility) - reduce confidence
            confidence *= 0.8
            logger.debug("Low volatility, reducing confidence")
        elif bandwidth > 0.08:
            # Very wide bands (high volatility) - reduce confidence
            confidence *= 0.9
            logger.debug("High volatility, reducing confidence")

        confidence = max(0.1, min(1.0, confidence))
        return signal, round(confidence, 2)

    def detect_squeeze(self, df: pd.DataFrame, threshold: float = 0.02) -> bool:
        """
        Detect Bollinger Band squeeze (low volatility, potential breakout)

        Args:
            df: DataFrame with 'close' column
            threshold: Bandwidth threshold for squeeze detection

        Returns:
            True if squeeze detected, False otherwise
        """
        bb_data = self.calculate(df)
        if bb_data is None:
            return False

        bandwidth = bb_data.get("bandwidth", 1.0)
        is_squeeze = bandwidth < threshold

        if is_squeeze:
            logger.info(f"BB Squeeze detected! Bandwidth: {bandwidth:.4f}")

        return is_squeeze

    def calculate_with_signal(
        self,
        df: pd.DataFrame
    ) -> Tuple[Optional[Dict[str, float]], SignalType, float]:
        """
        Calculate Bollinger Bands and generate signal in one call

        Args:
            df: DataFrame with 'close' column

        Returns:
            Tuple of (bb_dict, signal, confidence)
        """
        bb_data = self.calculate(df)

        if bb_data is None:
            return None, SignalType.NEUTRAL, 0.0

        signal, confidence = self.generate_signal(bb_data)

        # Boost confidence if squeeze detected (potential breakout)
        if self.detect_squeeze(df):
            confidence = min(1.0, confidence * 1.15)
            logger.info("Squeeze detected, boosting confidence")

        return bb_data, signal, confidence

    def calculate_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Bollinger Bands series for entire DataFrame

        Args:
            df: DataFrame with 'close' column

        Returns:
            DataFrame with upper_band, middle_band, lower_band columns
        """
        if len(df) < self.period:
            return pd.DataFrame()

        try:
            middle_band = df['close'].rolling(window=self.period).mean()
            std = df['close'].rolling(window=self.period).std()
            upper_band = middle_band + (std * self.std_dev)
            lower_band = middle_band - (std * self.std_dev)

            # Fixed: Calculate bandwidth with division by zero protection (Critical Issue #2)
            # When middle_band has 0 values, bandwidth calculation would crash
            # Replace 0 with inf to avoid division by zero (results in inf bandwidth for those rows)
            bandwidth = (upper_band - lower_band) / middle_band.replace(0, np.inf)

            result_df = pd.DataFrame({
                'upper_band': upper_band,
                'middle_band': middle_band,
                'lower_band': lower_band,
                'bandwidth': bandwidth
            })

            return result_df

        except Exception as e:
            logger.error(f"Error calculating BB series: {e}")
            return pd.DataFrame()
