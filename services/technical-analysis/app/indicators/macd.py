"""
MACD (Moving Average Convergence Divergence) Calculator
Purpose: Calculate MACD and generate trading signals
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple, Dict
from app.models import SignalType

logger = logging.getLogger(__name__)


class MACDCalculator:
    """
    Calculate MACD (Moving Average Convergence Divergence)

    MACD is a trend-following momentum indicator that shows the
    relationship between two moving averages of prices.

    Components:
        - MACD Line = EMA(12) - EMA(26)
        - Signal Line = EMA(9) of MACD Line
        - Histogram = MACD Line - Signal Line
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        """
        Initialize MACD calculator

        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.min_periods = slow_period + signal_period
        logger.info(f"MACD Calculator initialized: fast={fast_period}, slow={slow_period}, signal={signal_period}")

    def calculate(self, df: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        Calculate MACD components

        Args:
            df: DataFrame with 'close' column

        Returns:
            Dict with macd_line, signal_line, histogram or None if insufficient data
        """
        if len(df) < self.min_periods:
            logger.warning(f"Insufficient data for MACD: need {self.min_periods}, got {len(df)}")
            return None

        try:
            # Calculate EMAs
            ema_fast = df['close'].ewm(span=self.fast_period, adjust=False).mean()
            ema_slow = df['close'].ewm(span=self.slow_period, adjust=False).mean()

            # Calculate MACD line
            macd_line = ema_fast - ema_slow

            # Calculate signal line (EMA of MACD line)
            signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()

            # Calculate histogram
            histogram = macd_line - signal_line

            # Get current values
            result = {
                "macd_line": float(macd_line.iloc[-1]),
                "signal_line": float(signal_line.iloc[-1]),
                "histogram": float(histogram.iloc[-1])
            }

            logger.debug(f"Calculated MACD: {result}")
            return result

        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            return None

    def generate_signal(self, macd_data: Dict[str, float]) -> Tuple[SignalType, float]:
        """
        Generate trading signal based on MACD

        Args:
            macd_data: Dict with macd_line, signal_line, histogram

        Returns:
            Tuple of (SignalType, confidence)

        Signal Logic:
            - MACD crosses above Signal → BUY (bullish)
            - MACD crosses below Signal → SELL (bearish)
            - Histogram strength determines confidence
        """
        macd_line = macd_data["macd_line"]
        signal_line = macd_data["signal_line"]
        histogram = macd_data["histogram"]

        # Determine signal based on MACD position relative to signal line
        if histogram > 0:
            # MACD above signal line - bullish
            signal = SignalType.BUY

            # Confidence based on histogram magnitude
            # Larger positive histogram = stronger bullish signal
            confidence = min(1.0, abs(histogram) / (abs(macd_line) + 0.01) * 2)

            logger.info(f"MACD {macd_line:.2f} > Signal {signal_line:.2f} → BUY (hist: {histogram:.2f}, conf: {confidence:.2f})")

        elif histogram < 0:
            # MACD below signal line - bearish
            signal = SignalType.SELL

            # Confidence based on histogram magnitude
            confidence = min(1.0, abs(histogram) / (abs(macd_line) + 0.01) * 2)

            logger.info(f"MACD {macd_line:.2f} < Signal {signal_line:.2f} → SELL (hist: {histogram:.2f}, conf: {confidence:.2f})")

        else:
            # MACD equals signal line (rare) - neutral
            signal = SignalType.HOLD
            confidence = 0.1

            logger.debug("MACD equals Signal → HOLD")

        # Ensure minimum confidence
        confidence = max(0.1, min(1.0, confidence))

        return signal, round(confidence, 2)

    def detect_crossover(
        self,
        df: pd.DataFrame,
        lookback: int = 3
    ) -> Optional[str]:
        """
        Detect MACD crossover in recent periods

        Args:
            df: DataFrame with 'close' column
            lookback: Number of periods to check for crossover

        Returns:
            "bullish" for MACD crossing above signal
            "bearish" for MACD crossing below signal
            None if no crossover detected
        """
        if len(df) < self.min_periods + lookback:
            return None

        try:
            # Calculate MACD series
            ema_fast = df['close'].ewm(span=self.fast_period, adjust=False).mean()
            ema_slow = df['close'].ewm(span=self.slow_period, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
            histogram = macd_line - signal_line

            # Check recent periods for crossover
            recent_hist = histogram.tail(lookback).values

            # Bullish crossover: histogram goes from negative to positive
            if recent_hist[-1] > 0 and any(h < 0 for h in recent_hist[:-1]):
                logger.info("Detected bullish MACD crossover")
                return "bullish"

            # Bearish crossover: histogram goes from positive to negative
            if recent_hist[-1] < 0 and any(h > 0 for h in recent_hist[:-1]):
                logger.info("Detected bearish MACD crossover")
                return "bearish"

            return None

        except Exception as e:
            logger.error(f"Error detecting crossover: {e}")
            return None

    def calculate_with_signal(
        self,
        df: pd.DataFrame
    ) -> Tuple[Optional[Dict[str, float]], SignalType, float]:
        """
        Calculate MACD and generate signal in one call

        Args:
            df: DataFrame with 'close' column

        Returns:
            Tuple of (macd_dict, signal, confidence)
        """
        macd_data = self.calculate(df)

        if macd_data is None:
            return None, SignalType.NEUTRAL, 0.0

        signal, confidence = self.generate_signal(macd_data)

        # Boost confidence if crossover detected recently
        crossover = self.detect_crossover(df)
        if crossover:
            confidence = min(1.0, confidence * 1.2)  # 20% boost
            logger.info(f"Crossover detected, boosting confidence to {confidence:.2f}")

        return macd_data, signal, confidence

    def calculate_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate MACD series for entire DataFrame (for backtesting/analysis)

        Args:
            df: DataFrame with 'close' column

        Returns:
            DataFrame with macd_line, signal_line, histogram columns
        """
        if len(df) < self.min_periods:
            return pd.DataFrame()

        try:
            ema_fast = df['close'].ewm(span=self.fast_period, adjust=False).mean()
            ema_slow = df['close'].ewm(span=self.slow_period, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
            histogram = macd_line - signal_line

            result_df = pd.DataFrame({
                'macd_line': macd_line,
                'signal_line': signal_line,
                'histogram': histogram
            })

            return result_df

        except Exception as e:
            logger.error(f"Error calculating MACD series: {e}")
            return pd.DataFrame()
