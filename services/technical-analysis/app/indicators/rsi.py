"""
RSI (Relative Strength Index) Calculator
Purpose: Calculate RSI and generate trading signals
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple
from app.models import SignalType

logger = logging.getLogger(__name__)


class RSICalculator:
    """
    Calculate Relative Strength Index (RSI)

    RSI measures the magnitude of recent price changes to evaluate
    overbought or oversold conditions.

    Formula:
        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss
    """

    def __init__(self, period: int = 14):
        """
        Initialize RSI calculator

        Args:
            period: Number of periods for RSI calculation (default: 14)
        """
        self.period = period
        self.overbought_threshold = 70  # RSI > 70 = overbought (sell signal)
        self.oversold_threshold = 30   # RSI < 30 = oversold (buy signal)
        logger.info(f"RSI Calculator initialized with period={period}")

    def calculate(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate RSI from price data

        Args:
            df: DataFrame with 'close' column

        Returns:
            Current RSI value or None if insufficient data
        """
        if len(df) < self.period + 1:
            logger.warning(f"Insufficient data for RSI: need {self.period + 1}, got {len(df)}")
            return None

        try:
            # Calculate price changes
            delta = df['close'].diff()

            # Separate gains and losses
            gains = delta.where(delta > 0, 0.0)
            losses = -delta.where(delta < 0, 0.0)

            # Calculate average gain and loss using Wilder's smoothing method
            avg_gain = gains.ewm(alpha=1/self.period, min_periods=self.period, adjust=False).mean()
            avg_loss = losses.ewm(alpha=1/self.period, min_periods=self.period, adjust=False).mean()

            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # Get the most recent RSI value
            current_rsi = rsi.iloc[-1]

            logger.debug(f"Calculated RSI: {current_rsi:.2f}")
            return float(current_rsi)

        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None

    def generate_signal(self, rsi: float) -> Tuple[SignalType, float]:
        """
        Generate trading signal based on RSI value

        Args:
            rsi: Current RSI value

        Returns:
            Tuple of (SignalType, confidence)

        Signal Logic:
            - RSI < 30: Strong BUY (oversold)
            - RSI < 40: Weak BUY
            - RSI 40-60: HOLD/NEUTRAL
            - RSI > 60: Weak SELL
            - RSI > 70: Strong SELL (overbought)
        """
        # Calculate confidence based on distance from thresholds
        if rsi < self.oversold_threshold:
            # Oversold - BUY signal
            # Confidence increases as RSI gets lower
            confidence = min(1.0, (self.oversold_threshold - rsi) / self.oversold_threshold)
            signal = SignalType.BUY
            logger.info(f"RSI {rsi:.2f} < {self.oversold_threshold} → BUY (confidence: {confidence:.2f})")

        elif rsi > self.overbought_threshold:
            # Overbought - SELL signal
            # Confidence increases as RSI gets higher
            confidence = min(1.0, (rsi - self.overbought_threshold) / (100 - self.overbought_threshold))
            signal = SignalType.SELL
            logger.info(f"RSI {rsi:.2f} > {self.overbought_threshold} → SELL (confidence: {confidence:.2f})")

        elif rsi < 40:
            # Slightly oversold - weak BUY
            confidence = (40 - rsi) / 10 * 0.5  # Max 0.5 confidence
            signal = SignalType.BUY
            logger.debug(f"RSI {rsi:.2f} slightly low → weak BUY")

        elif rsi > 60:
            # Slightly overbought - weak SELL
            confidence = (rsi - 60) / 10 * 0.5  # Max 0.5 confidence
            signal = SignalType.SELL
            logger.debug(f"RSI {rsi:.2f} slightly high → weak SELL")

        else:
            # Neutral range (40-60)
            signal = SignalType.HOLD
            confidence = 0.3  # Low confidence for hold
            logger.debug(f"RSI {rsi:.2f} neutral → HOLD")

        return signal, round(confidence, 2)

    def calculate_with_signal(
        self,
        df: pd.DataFrame
    ) -> Tuple[Optional[float], SignalType, float]:
        """
        Calculate RSI and generate signal in one call

        Args:
            df: DataFrame with 'close' column

        Returns:
            Tuple of (rsi_value, signal, confidence)
        """
        rsi = self.calculate(df)

        if rsi is None:
            return None, SignalType.NEUTRAL, 0.0

        signal, confidence = self.generate_signal(rsi)
        return rsi, signal, confidence

    def calculate_series(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate RSI for entire DataFrame (for backtesting/analysis)

        Args:
            df: DataFrame with 'close' column

        Returns:
            Series of RSI values
        """
        if len(df) < self.period + 1:
            return pd.Series(dtype=float)

        try:
            delta = df['close'].diff()
            gains = delta.where(delta > 0, 0.0)
            losses = -delta.where(delta < 0, 0.0)

            avg_gain = gains.ewm(alpha=1/self.period, min_periods=self.period, adjust=False).mean()
            avg_loss = losses.ewm(alpha=1/self.period, min_periods=self.period, adjust=False).mean()

            rs = avg_gain / avg_loss
            rsi_series = 100 - (100 / (1 + rs))

            return rsi_series

        except Exception as e:
            logger.error(f"Error calculating RSI series: {e}")
            return pd.Series(dtype=float)
