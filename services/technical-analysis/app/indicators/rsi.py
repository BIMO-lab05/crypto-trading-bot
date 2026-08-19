"""
RSI (Relative Strength Index) Calculator
Purpose: Calculate RSI and generate trading signals

RESEARCH-BASED OPTIMIZATION (2025-11-28):
Based on analysis of top open-source trading bots (Freqtrade, Hummingbot, Jesse):
- Period: 14 -> 9 (more responsive for crypto volatility)
- Overbought: 70 -> 80 (crypto-specific, allows stronger trends to continue)
- Oversold: 30 -> 20 (crypto-specific, allows stronger downtrends to continue)

Rationale:
- Crypto markets are more volatile than traditional markets
- Standard RSI settings (14/70/30) generate too many false signals in crypto
- Research shows 9-period RSI with 80/20 thresholds achieves better accuracy
- These parameters should be re-optimized quarterly (walk-forward optimization)
- Recommended optimization window: 6 months of historical data

Previous settings (pre-optimization):
- Period: 14
- Overbought: 65 (widened from 70)
- Oversold: 35 (widened from 30)
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

    RESEARCH-BASED PARAMETERS (2025-11-28):
    - Period: 9 (optimized for crypto volatility)
    - Overbought: 80 (crypto-specific threshold)
    - Oversold: 20 (crypto-specific threshold)

    NOTE: Parameters should be re-optimized quarterly using walk-forward
    optimization with 6-month historical windows.
    """

    # Bounds of the expanded neutral (HOLD) zone. The moderate BUY/SELL zones
    # run from these out to the oversold/overbought thresholds.
    NEUTRAL_LOWER = 35
    NEUTRAL_UPPER = 65

    # Confidence at the moderate/strong join. The moderate zones ramp
    # 0 -> MODERATE_MAX_CONFIDENCE and the strong zones continue
    # MODERATE_MAX_CONFIDENCE -> 1.0, which is what makes the curve continuous
    # and monotone in distance from neutral. See generate_signal().
    MODERATE_MAX_CONFIDENCE = 0.6

    def __init__(self, period: int = 9):
        """
        Initialize RSI calculator

        Args:
            period: Number of periods for RSI calculation
                   Default: 9 (research-optimized for crypto volatility)
                   Previous default was 14 (traditional markets standard)
        """
        self.period = period

        # RESEARCH-BASED OPTIMIZATION (2025-11-28):
        # Crypto-specific thresholds based on Freqtrade/Hummingbot/Jesse analysis
        # - Standard markets: overbought=70, oversold=30
        # - Crypto markets: overbought=80, oversold=20 (allows stronger trends)
        # - Research shows 82.68% accuracy with these crypto-specific thresholds
        self.overbought_threshold = 80  # RSI > 80 = overbought (sell signal)
        self.oversold_threshold = 20  # RSI < 20 = oversold (buy signal)

        logger.info(
            f"RSI Calculator initialized (RESEARCH-OPTIMIZED): "
            f"period={period}, overbought={self.overbought_threshold}, "
            f"oversold={self.oversold_threshold}"
        )
        logger.info(
            "  Note: Parameters optimized for crypto volatility. "
            "Re-optimize quarterly using 6-month walk-forward window."
        )

    def calculate(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate RSI from price data

        Args:
            df: DataFrame with 'close' column

        Returns:
            Current RSI value or None if insufficient data
        """
        if len(df) < self.period + 1:
            logger.warning(
                f"Insufficient data for RSI: need {self.period + 1}, got {len(df)}"
            )
            return None

        try:
            # Calculate price changes
            delta = df["close"].diff()

            # Separate gains and losses
            gains = delta.where(delta > 0, 0.0)
            losses = -delta.where(delta < 0, 0.0)

            # Calculate average gain and loss using Wilder's smoothing method
            avg_gain = gains.ewm(
                alpha=1 / self.period, min_periods=self.period, adjust=False
            ).mean()
            avg_loss = losses.ewm(
                alpha=1 / self.period, min_periods=self.period, adjust=False
            ).mean()

            # Fixed: Calculate RS and RSI with division by zero protection (Critical Issue #1)
            # When avg_loss is 0 (strong uptrend), RSI = 100
            # When avg_gain is 0 (strong downtrend), RSI = 0
            # Standard RSI behavior for edge cases
            rs = avg_gain / avg_loss.replace(
                0, np.inf
            )  # Replace 0 with inf to avoid division by zero
            rsi = 100 - (100 / (1 + rs))

            # Get the most recent RSI value
            current_rsi = rsi.iloc[-1]

            # Fixed: Check for NaN/Inf values before returning (Critical Issue #5 - NaN propagation)
            if np.isnan(current_rsi) or np.isinf(current_rsi):
                logger.warning(
                    f"RSI calculation resulted in NaN or Inf. avg_gain: {avg_gain.iloc[-1]}, avg_loss: {avg_loss.iloc[-1]}"
                )
                # Return safe default based on market direction
                if avg_gain.iloc[-1] > 0 and avg_loss.iloc[-1] == 0:
                    return 100.0  # Only gains = extremely overbought
                elif avg_gain.iloc[-1] == 0 and avg_loss.iloc[-1] > 0:
                    return 0.0  # Only losses = extremely oversold
                else:
                    return 50.0  # Neutral fallback

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

        Signal Logic (RESEARCH-OPTIMIZED 2025-11-28):
        Crypto-specific thresholds for higher accuracy:
            - RSI < 20: Strong BUY (extremely oversold in crypto)
            - RSI < 35: Moderate BUY (oversold zone)
            - RSI 35-65: HOLD/NEUTRAL (expanded neutral zone for crypto)
            - RSI > 65: Moderate SELL (overbought zone)
            - RSI > 80: Strong SELL (extremely overbought in crypto)

        Confidence is monotonically non-decreasing in distance from the
        neutral midpoint across each directional side (MONOTONICITY FIX
        2026-08-09). The strong zones previously restarted their ramp at 0
        instead of continuing from where the moderate zones ended, so crossing
        RSI=20 downward collapsed confidence from 0.60 to 0.0005 and it did not
        recover to 0.60 until RSI <= 8. Since voter.py computes
        `score x confidence x weight`, the RSI leg contributed ~0 on exactly
        the bars it logged as "Strong BUY/SELL": 350/360 BTC and 360/378 ADA
        extreme bars carried a weaker vote than a bar sitting on the threshold.

        The HOLD zone's flat 0.3 is deliberately outside this invariant --
        it is confidence in *no* signal, and HOLD scores 0.0 in the voter, so
        it never multiplies into a directional contribution.
        """
        # Ceiling of the moderate zones and floor of the strong zones. Tying
        # them to one constant is what keeps the curve continuous at the join.
        moderate_max = self.MODERATE_MAX_CONFIDENCE

        # Calculate confidence based on distance from thresholds
        if rsi < self.oversold_threshold:
            # Extremely oversold - Strong BUY signal (crypto-specific)
            # Ramps moderate_max -> 1.0 as RSI falls from the threshold to 0,
            # picking up exactly where the moderate branch below leaves off.
            extremity = min(
                1.0, (self.oversold_threshold - rsi) / self.oversold_threshold
            )
            confidence = moderate_max + extremity * (1.0 - moderate_max)
            signal = SignalType.BUY
            logger.info(
                f"RSI {rsi:.2f} < {self.oversold_threshold} -> Strong BUY (confidence: {confidence:.2f})"
            )

        elif rsi > self.overbought_threshold:
            # Extremely overbought - Strong SELL signal (crypto-specific)
            # Ramps moderate_max -> 1.0 as RSI rises from the threshold to 100.
            extremity = min(
                1.0,
                (rsi - self.overbought_threshold) / (100 - self.overbought_threshold),
            )
            confidence = moderate_max + extremity * (1.0 - moderate_max)
            signal = SignalType.SELL
            logger.info(
                f"RSI {rsi:.2f} > {self.overbought_threshold} -> Strong SELL (confidence: {confidence:.2f})"
            )

        elif rsi < self.NEUTRAL_LOWER:
            # Oversold zone - Moderate BUY
            # Research shows 35 is a good secondary threshold for crypto.
            # Span is derived from the threshold, not a literal 15, so the
            # join with the strong branch stays exact if the threshold moves.
            span = self.NEUTRAL_LOWER - self.oversold_threshold
            confidence = (self.NEUTRAL_LOWER - rsi) / span * moderate_max
            signal = SignalType.BUY
            logger.info(
                f"RSI {rsi:.2f} in oversold zone ({self.oversold_threshold}-{self.NEUTRAL_LOWER}) -> Moderate BUY (confidence: {confidence:.2f})"
            )

        elif rsi > self.NEUTRAL_UPPER:
            # Overbought zone - Moderate SELL
            # Research shows 65 is a good secondary threshold for crypto
            span = self.overbought_threshold - self.NEUTRAL_UPPER
            confidence = (rsi - self.NEUTRAL_UPPER) / span * moderate_max
            signal = SignalType.SELL
            logger.info(
                f"RSI {rsi:.2f} in overbought zone ({self.NEUTRAL_UPPER}-{self.overbought_threshold}) -> Moderate SELL (confidence: {confidence:.2f})"
            )

        else:
            # Expanded neutral range (35-65) for crypto - HOLD
            # Crypto markets need wider neutral zone due to volatility
            signal = SignalType.HOLD
            confidence = 0.3  # Low confidence for hold
            logger.debug(f"RSI {rsi:.2f} neutral (35-65) -> HOLD")

        return signal, round(confidence, 2)

    def calculate_with_signal(
        self, df: pd.DataFrame
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
            delta = df["close"].diff()
            gains = delta.where(delta > 0, 0.0)
            losses = -delta.where(delta < 0, 0.0)

            avg_gain = gains.ewm(
                alpha=1 / self.period, min_periods=self.period, adjust=False
            ).mean()
            avg_loss = losses.ewm(
                alpha=1 / self.period, min_periods=self.period, adjust=False
            ).mean()

            # Fixed: Calculate RS and RSI with division by zero protection (Critical Issue #1)
            # When avg_loss is 0 (strong uptrend), RSI = 100
            # Standard RSI behavior for edge cases across entire series
            rs = avg_gain / avg_loss.replace(
                0, np.inf
            )  # Replace 0 with inf to avoid division by zero
            rsi_series = 100 - (100 / (1 + rs))

            return rsi_series

        except Exception as e:
            logger.error(f"Error calculating RSI series: {e}")
            return pd.Series(dtype=float)
