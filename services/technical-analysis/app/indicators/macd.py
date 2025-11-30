"""
MACD (Moving Average Convergence Divergence) Calculator
Purpose: Calculate MACD and generate trading signals

RESEARCH-BASED OPTIMIZATION (2025-11-29):
Based on Kang 2021 Study and comprehensive backtesting analysis:

OPTIMAL PARAMETERS: 5-35-5 (RESEARCH-BACKED - DEFAULT)
- Fast EMA: 5 (short-term momentum capture)
- Slow EMA: 35 (longer trend confirmation)
- Signal Line: 5 (faster signal response)

ALTERNATIVE: LINDA RASCHKE 3-10-16 (Day Trading)
- Fast EMA: 3 (ultra-responsive to price action)
- Slow EMA: 10 (short-term trend)
- Signal Line: 16 (filters noise while capturing pullbacks)
- Best for: Day trading, pullback entries in strong trends

RESEARCH RESULTS (Kang 2021):
- Standard 12-26-9: -3.6% annual return
- Optimized 5-35-5: +11.0% annual return
- Improvement: +14.6% annual outperformance

LINDA RASCHKE 3-10-16 BENEFITS:
- More responsive to recent price action
- Excellent for identifying pullbacks in strong trends
- Faster settings (3-10) capture momentum quicker
- Longer signal (16) filters out noise better than standard 9

CONFIGURATION OPTIONS:
- "kang2021": 5-35-5 (default, swing trading)
- "raschke": 3-10-16 (day trading, pullbacks)
- "standard": 12-26-9 (classic, reference only)

NOTE: Re-optimize quarterly using walk-forward analysis
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
        - MACD Line = EMA(fast) - EMA(slow)
        - Signal Line = EMA(signal) of MACD Line
        - Histogram = MACD Line - Signal Line

    RESEARCH-BASED PARAMETERS (2025-11-29 - Kang 2021 Study):
    - Fast EMA: 5 (captures short-term momentum)
    - Slow EMA: 35 (stable trend baseline)
    - Signal Line: 5 (fast signal response)

    PERFORMANCE:
    - Standard 12-26-9: -3.6% annual
    - Optimized 5-35-5: +11.0% annual
    - Net improvement: +14.6%

    NOTE: Re-optimize quarterly using walk-forward analysis
    """

    # RESEARCH-BACKED PRESET CONFIGURATIONS
    PRESETS = {
        "kang2021": {"fast": 5, "slow": 35, "signal": 5},      # Default - Swing trading
        "raschke": {"fast": 3, "slow": 10, "signal": 16},      # Day trading, pullbacks
        "standard": {"fast": 12, "slow": 26, "signal": 9},     # Classic reference
        "crypto_volatile": {"fast": 8, "slow": 21, "signal": 9}, # High volatility periods
    }

    @classmethod
    def from_preset(cls, preset_name: str = "kang2021") -> "MACDCalculator":
        """
        Create MACD calculator from a research-backed preset

        Available presets:
        - "kang2021": 5-35-5 (default, +14.6% over standard, swing trading)
        - "raschke": 3-10-16 (Linda Raschke, day trading, pullback entries)
        - "standard": 12-26-9 (classic, for reference only)
        - "crypto_volatile": 8-21-9 (high volatility periods)

        Args:
            preset_name: Name of the preset configuration

        Returns:
            MACDCalculator instance with preset parameters
        """
        if preset_name not in cls.PRESETS:
            logger.warning(f"Unknown preset '{preset_name}', using 'kang2021'")
            preset_name = "kang2021"

        preset = cls.PRESETS[preset_name]
        logger.info(f"Creating MACD with '{preset_name}' preset: {preset}")
        return cls(
            fast_period=preset["fast"],
            slow_period=preset["slow"],
            signal_period=preset["signal"]
        )

    def __init__(self, fast_period: int = 5, slow_period: int = 35, signal_period: int = 5):
        """
        Initialize MACD calculator

        Args:
            fast_period: Fast EMA period
                        Default: 5 (Kang 2021 research-optimized)
                        Previous: 8/12 (earlier optimizations)
            slow_period: Slow EMA period
                        Default: 35 (Kang 2021 research-optimized)
                        Previous: 17/26 (earlier optimizations)
            signal_period: Signal line EMA period
                          Default: 5 (Kang 2021 research-optimized)
                          Previous: 9 (standard smoothing)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.min_periods = slow_period + signal_period

        logger.info(
            f"MACD Calculator initialized (RESEARCH-OPTIMIZED): "
            f"fast={fast_period}, slow={slow_period}, signal={signal_period}"
        )
        logger.info(
            "  Note: Parameters optimized for crypto volatility. "
            "Re-optimize quarterly using 6-month walk-forward window."
        )

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
            - MACD crosses above Signal -> BUY (bullish)
            - MACD crosses below Signal -> SELL (bearish)
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

            logger.info(f"MACD {macd_line:.2f} > Signal {signal_line:.2f} -> BUY (hist: {histogram:.2f}, conf: {confidence:.2f})")

        elif histogram < 0:
            # MACD below signal line - bearish
            signal = SignalType.SELL

            # Confidence based on histogram magnitude
            confidence = min(1.0, abs(histogram) / (abs(macd_line) + 0.01) * 2)

            logger.info(f"MACD {macd_line:.2f} < Signal {signal_line:.2f} -> SELL (hist: {histogram:.2f}, conf: {confidence:.2f})")

        else:
            # MACD equals signal line (rare) - neutral
            signal = SignalType.HOLD
            confidence = 0.1

            logger.debug("MACD equals Signal -> HOLD")

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
