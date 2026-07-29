"""
Moving Averages Calculators (SMA and EMA)
Purpose: Calculate moving averages and generate trading signals
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple
from app.models import SignalType

logger = logging.getLogger(__name__)


class SMACalculator:
    """
    Calculate Simple Moving Average (SMA)

    SMA is the average price over a specified number of periods.
    All prices are weighted equally.
    """

    def __init__(self, period: int = 20):
        """
        Initialize SMA calculator

        Args:
            period: Number of periods (default: 20)
        """
        self.period = period
        logger.info(f"SMA Calculator initialized: period={period}")

    def calculate(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate SMA

        Args:
            df: DataFrame with 'close' column

        Returns:
            Current SMA value or None if insufficient data
        """
        if len(df) < self.period:
            logger.warning(f"Insufficient data for SMA: need {self.period}, got {len(df)}")
            return None

        try:
            sma = df['close'].rolling(window=self.period).mean()
            current_sma = float(sma.iloc[-1])

            logger.debug(f"Calculated SMA({self.period}): {current_sma:.2f}")
            return current_sma

        except Exception as e:
            logger.error(f"Error calculating SMA: {e}")
            return None

    def generate_signal(
        self,
        sma: float,
        current_price: float
    ) -> Tuple[SignalType, float]:
        """
        Generate trading signal based on price vs SMA

        Args:
            sma: Current SMA value
            current_price: Current price

        Returns:
            Tuple of (SignalType, confidence)

        Signal Logic:
            - Price > SMA: Bullish (BUY)
            - Price < SMA: Bearish (SELL)
            - Distance from SMA affects confidence
        """
        price_diff_pct = ((current_price - sma) / sma) * 100

        # Data-error guard (audit 2026-07): a price more than 30% away from
        # its own SMA is not a tradable divergence — it indicates corrupt
        # input (e.g. testnet pollution). Do not emit a max-confidence
        # directional signal on garbage; return HOLD with 0 confidence.
        if abs(price_diff_pct) > 30:
            logger.warning(
                f"SMA signal suppressed: price {current_price:.2f} is "
                f"{price_diff_pct:+.2f}% from SMA {sma:.2f} (>30% - "
                f"treating as data error)"
            )
            return SignalType.HOLD, 0.0

        if price_diff_pct > 0:
            # Price above SMA - bullish
            signal = SignalType.BUY
            # Confidence based on distance above SMA
            confidence = min(1.0, abs(price_diff_pct) / 5)  # Max confidence at 5% above
            logger.info(f"Price {current_price:.2f} > SMA {sma:.2f} ({price_diff_pct:+.2f}%) → BUY")

        elif price_diff_pct < 0:
            # Price below SMA - bearish
            signal = SignalType.SELL
            # Confidence based on distance below SMA
            confidence = min(1.0, abs(price_diff_pct) / 5)  # Max confidence at 5% below
            logger.info(f"Price {current_price:.2f} < SMA {sma:.2f} ({price_diff_pct:+.2f}%) → SELL")

        else:
            # Price at SMA
            signal = SignalType.HOLD
            confidence = 0.1

        confidence = max(0.1, min(1.0, confidence))
        return signal, round(confidence, 2)

    def detect_crossover(
        self,
        df: pd.DataFrame,
        lookback: int = 3
    ) -> Optional[str]:
        """
        Detect price crossing SMA

        Args:
            df: DataFrame with 'close' column
            lookback: Periods to check for crossover

        Returns:
            "bullish" for price crossing above SMA
            "bearish" for price crossing below SMA
            None if no crossover
        """
        if len(df) < self.period + lookback:
            return None

        try:
            sma = df['close'].rolling(window=self.period).mean()
            price = df['close']

            # Check recent periods
            recent_price = price.tail(lookback).values
            recent_sma = sma.tail(lookback).values

            # Bullish crossover: price crosses above SMA
            if recent_price[-1] > recent_sma[-1] and any(p < s for p, s in zip(recent_price[:-1], recent_sma[:-1])):
                logger.info(f"Detected bullish SMA({self.period}) crossover")
                return "bullish"

            # Bearish crossover: price crosses below SMA
            if recent_price[-1] < recent_sma[-1] and any(p > s for p, s in zip(recent_price[:-1], recent_sma[:-1])):
                logger.info(f"Detected bearish SMA({self.period}) crossover")
                return "bearish"

            return None

        except Exception as e:
            logger.error(f"Error detecting crossover: {e}")
            return None


class EMACalculator:
    """
    Calculate Exponential Moving Average (EMA)

    EMA gives more weight to recent prices, making it more
    responsive to new information than SMA.
    """

    def __init__(self, period: int = 20):
        """
        Initialize EMA calculator

        Args:
            period: Number of periods (default: 20)
        """
        self.period = period
        logger.info(f"EMA Calculator initialized: period={period}")

    def calculate(self, df: pd.DataFrame) -> Optional[float]:
        """
        Calculate EMA

        Args:
            df: DataFrame with 'close' column

        Returns:
            Current EMA value or None if insufficient data
        """
        if len(df) < self.period:
            logger.warning(f"Insufficient data for EMA: need {self.period}, got {len(df)}")
            return None

        try:
            ema = df['close'].ewm(span=self.period, adjust=False).mean()
            current_ema = float(ema.iloc[-1])

            logger.debug(f"Calculated EMA({self.period}): {current_ema:.2f}")
            return current_ema

        except Exception as e:
            logger.error(f"Error calculating EMA: {e}")
            return None

    def generate_signal(
        self,
        ema: float,
        current_price: float
    ) -> Tuple[SignalType, float]:
        """
        Generate trading signal based on price vs EMA

        Args:
            ema: Current EMA value
            current_price: Current price

        Returns:
            Tuple of (SignalType, confidence)
        """
        price_diff_pct = ((current_price - ema) / ema) * 100

        # Data-error guard (audit 2026-07): >30% divergence from the EMA is
        # corrupt input, not signal — see SMACalculator.generate_signal.
        if abs(price_diff_pct) > 30:
            logger.warning(
                f"EMA signal suppressed: price {current_price:.2f} is "
                f"{price_diff_pct:+.2f}% from EMA {ema:.2f} (>30% - "
                f"treating as data error)"
            )
            return SignalType.HOLD, 0.0

        if price_diff_pct > 0:
            # Price above EMA - bullish
            signal = SignalType.BUY
            confidence = min(1.0, abs(price_diff_pct) / 5)
            logger.info(f"Price {current_price:.2f} > EMA {ema:.2f} ({price_diff_pct:+.2f}%) → BUY")

        elif price_diff_pct < 0:
            # Price below EMA - bearish
            signal = SignalType.SELL
            confidence = min(1.0, abs(price_diff_pct) / 5)
            logger.info(f"Price {current_price:.2f} < EMA {ema:.2f} ({price_diff_pct:+.2f}%) → SELL")

        else:
            signal = SignalType.HOLD
            confidence = 0.1

        confidence = max(0.1, min(1.0, confidence))
        return signal, round(confidence, 2)

    def detect_crossover(
        self,
        df: pd.DataFrame,
        lookback: int = 3
    ) -> Optional[str]:
        """
        Detect price crossing EMA

        Args:
            df: DataFrame with 'close' column
            lookback: Periods to check for crossover

        Returns:
            "bullish", "bearish", or None
        """
        if len(df) < self.period + lookback:
            return None

        try:
            ema = df['close'].ewm(span=self.period, adjust=False).mean()
            price = df['close']

            recent_price = price.tail(lookback).values
            recent_ema = ema.tail(lookback).values

            # Bullish crossover
            if recent_price[-1] > recent_ema[-1] and any(p < e for p, e in zip(recent_price[:-1], recent_ema[:-1])):
                logger.info(f"Detected bullish EMA({self.period}) crossover")
                return "bullish"

            # Bearish crossover
            if recent_price[-1] < recent_ema[-1] and any(p > e for p, e in zip(recent_price[:-1], recent_ema[:-1])):
                logger.info(f"Detected bearish EMA({self.period}) crossover")
                return "bearish"

            return None

        except Exception as e:
            logger.error(f"Error detecting crossover: {e}")
            return None


class MAGoldenCrossDetector:
    """
    Detect Golden Cross and Death Cross
    Golden Cross: Fast MA crosses above Slow MA (bullish)
    Death Cross: Fast MA crosses below Slow MA (bearish)
    """

    def __init__(self, fast_period: int = 50, slow_period: int = 200):
        """
        Initialize detector

        Args:
            fast_period: Fast MA period (default: 50)
            slow_period: Slow MA period (default: 200)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        logger.info(f"MA Cross Detector initialized: fast={fast_period}, slow={slow_period}")

    def detect(self, df: pd.DataFrame, lookback: int = 5) -> Optional[str]:
        """
        Detect Golden Cross or Death Cross

        Args:
            df: DataFrame with 'close' column
            lookback: Periods to check for cross

        Returns:
            "golden_cross", "death_cross", or None
        """
        if len(df) < self.slow_period + lookback:
            return None

        try:
            fast_ma = df['close'].rolling(window=self.fast_period).mean()
            slow_ma = df['close'].rolling(window=self.slow_period).mean()

            recent_fast = fast_ma.tail(lookback).values
            recent_slow = slow_ma.tail(lookback).values

            # Golden Cross: fast crosses above slow
            if recent_fast[-1] > recent_slow[-1] and any(f < s for f, s in zip(recent_fast[:-1], recent_slow[:-1])):
                logger.info(f"🟢 GOLDEN CROSS detected! MA({self.fast_period}) > MA({self.slow_period})")
                return "golden_cross"

            # Death Cross: fast crosses below slow
            if recent_fast[-1] < recent_slow[-1] and any(f > s for f, s in zip(recent_fast[:-1], recent_slow[:-1])):
                logger.info(f"🔴 DEATH CROSS detected! MA({self.fast_period}) < MA({self.slow_period})")
                return "death_cross"

            return None

        except Exception as e:
            logger.error(f"Error detecting MA cross: {e}")
            return None
