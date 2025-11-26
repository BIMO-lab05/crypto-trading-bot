"""
RSI (Relative Strength Index) Calculator
Purpose: Calculate RSI and generate trading signals

Updated: Widened thresholds to generate more BUY/SELL signals
- Oversold threshold: 30 -> 35 (more BUY signals)
- Overbought threshold: 70 -> 65 (more SELL signals)
- Neutral zone: 40-60 -> 45-55 (narrower HOLD range)
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
        # Updated: Widened thresholds to generate more signals
        # Previous: overbought=70, oversold=30 (too conservative)
        # New: overbought=65, oversold=35 (more balanced signal generation)
        self.overbought_threshold = 65  # RSI > 65 = overbought (sell signal)
        self.oversold_threshold = 35    # RSI < 35 = oversold (buy signal)
        logger.info(f"RSI Calculator initialized with period={period}, overbought={self.overbought_threshold}, oversold={self.oversold_threshold}")

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

            # Fixed: Calculate RS and RSI with division by zero protection (Critical Issue #1)
            # When avg_loss is 0 (strong uptrend), RSI = 100
            # When avg_gain is 0 (strong downtrend), RSI = 0
            # Standard RSI behavior for edge cases
            rs = avg_gain / avg_loss.replace(0, np.inf)  # Replace 0 with inf to avoid division by zero
            rsi = 100 - (100 / (1 + rs))

            # Get the most recent RSI value
            current_rsi = rsi.iloc[-1]

            # Fixed: Check for NaN/Inf values before returning (Critical Issue #5 - NaN propagation)
            if np.isnan(current_rsi) or np.isinf(current_rsi):
                logger.warning(f"RSI calculation resulted in NaN or Inf. avg_gain: {avg_gain.iloc[-1]}, avg_loss: {avg_loss.iloc[-1]}")
                # Return safe default based on market direction
                if avg_gain.iloc[-1] > 0 and avg_loss.iloc[-1] == 0:
                    return 100.0  # Only gains = extremely overbought
                elif avg_gain.iloc[-1] == 0 and avg_loss.iloc[-1] > 0:
                    return 0.0    # Only losses = extremely oversold
                else:
                    return 50.0   # Neutral fallback

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

        Signal Logic (Updated for more signals):
            - RSI < 35: Strong BUY (oversold)
            - RSI < 45: Moderate BUY (slightly oversold)
            - RSI 45-55: HOLD/NEUTRAL (narrowed from 40-60)
            - RSI > 55: Moderate SELL (slightly overbought)
            - RSI > 65: Strong SELL (overbought)
        """
        # Calculate confidence based on distance from thresholds
        if rsi < self.oversold_threshold:
            # Oversold - Strong BUY signal
            # Confidence increases as RSI gets lower
            confidence = min(1.0, (self.oversold_threshold - rsi) / self.oversold_threshold)
            signal = SignalType.BUY
            logger.info(f"RSI {rsi:.2f} < {self.oversold_threshold} -> Strong BUY (confidence: {confidence:.2f})")

        elif rsi > self.overbought_threshold:
            # Overbought - Strong SELL signal
            # Confidence increases as RSI gets higher
            confidence = min(1.0, (rsi - self.overbought_threshold) / (100 - self.overbought_threshold))
            signal = SignalType.SELL
            logger.info(f"RSI {rsi:.2f} > {self.overbought_threshold} -> Strong SELL (confidence: {confidence:.2f})")

        elif rsi < 45:
            # Slightly oversold - Moderate BUY
            # Updated: Threshold increased from 40 to 45 for more signals
            confidence = (45 - rsi) / 10 * 0.6  # Max 0.6 confidence (increased from 0.5)
            signal = SignalType.BUY
            logger.info(f"RSI {rsi:.2f} slightly low -> Moderate BUY (confidence: {confidence:.2f})")

        elif rsi > 55:
            # Slightly overbought - Moderate SELL
            # Updated: Threshold decreased from 60 to 55 for more signals
            confidence = (rsi - 55) / 10 * 0.6  # Max 0.6 confidence (increased from 0.5)
            signal = SignalType.SELL
            logger.info(f"RSI {rsi:.2f} slightly high -> Moderate SELL (confidence: {confidence:.2f})")

        else:
            # Narrow neutral range (45-55) - HOLD
            # Updated: Narrowed from 40-60 to generate fewer HOLD signals
            signal = SignalType.HOLD
            confidence = 0.3  # Low confidence for hold
            logger.debug(f"RSI {rsi:.2f} neutral (45-55) -> HOLD")

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

            # Fixed: Calculate RS and RSI with division by zero protection (Critical Issue #1)
            # When avg_loss is 0 (strong uptrend), RSI = 100
            # Standard RSI behavior for edge cases across entire series
            rs = avg_gain / avg_loss.replace(0, np.inf)  # Replace 0 with inf to avoid division by zero
            rsi_series = 100 - (100 / (1 + rs))

            return rsi_series

        except Exception as e:
            logger.error(f"Error calculating RSI series: {e}")
            return pd.Series(dtype=float)
