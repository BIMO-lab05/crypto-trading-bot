"""
ADX (Average Directional Index) Indicator
Purpose: Measures trend strength and provides market regime classification
Author: Backend Developer Agent
Date: 2025-11-28

ADX Values Interpretation:
- ADX > 25: Strong trend (TRENDING market)
- ADX 20-25: Weak trend (WEAK_TREND market)
- ADX < 20: No clear trend (RANGING market)

Components:
- +DI (Positive Directional Indicator): Measures upward movement strength
- -DI (Negative Directional Indicator): Measures downward movement strength
- ADX: Smoothed average of the absolute difference between +DI and -DI

Trading Applications:
- Use trend-following strategies when ADX > 25
- Use mean-reversion strategies when ADX < 20
- +DI > -DI suggests bullish momentum
- -DI > +DI suggests bearish momentum
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """
    Market regime classification based on ADX values

    STRONG_TREND: ADX > 30, clear directional movement
    TRENDING: ADX 25-30, moderate trend strength
    WEAK_TREND: ADX 20-25, emerging or fading trend
    RANGING: ADX < 20, sideways/choppy market
    """
    STRONG_TREND = "STRONG_TREND"
    TRENDING = "TRENDING"
    WEAK_TREND = "WEAK_TREND"
    RANGING = "RANGING"


class TrendDirection(str, Enum):
    """
    Trend direction based on +DI/-DI comparison

    BULLISH: +DI > -DI (upward momentum dominates)
    BEARISH: -DI > +DI (downward momentum dominates)
    NEUTRAL: +DI approximately equals -DI
    """
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class ADXCalculator:
    """
    ADX (Average Directional Index) Calculator

    Calculates Wilder's ADX indicator for trend strength measurement.

    Key Features:
    - ADX value (0-100): Trend strength regardless of direction
    - +DI value: Positive directional indicator
    - -DI value: Negative directional indicator
    - Market regime classification: TRENDING, RANGING, WEAK_TREND
    - Trend direction: BULLISH, BEARISH, NEUTRAL

    Formula:
    1. Calculate True Range (TR)
    2. Calculate +DM and -DM (Directional Movement)
    3. Smooth +DM, -DM, and TR using Wilder's smoothing
    4. Calculate +DI = 100 * smoothed(+DM) / smoothed(TR)
    5. Calculate -DI = 100 * smoothed(-DM) / smoothed(TR)
    6. Calculate DX = 100 * |+DI - -DI| / (+DI + -DI)
    7. Calculate ADX = Wilder's smoothing of DX

    Parameters:
        period: Lookback period for smoothing (default: 14)
        trending_threshold: ADX value above which market is TRENDING (default: 25)
        weak_trend_threshold: ADX value for WEAK_TREND boundary (default: 20)
        strong_trend_threshold: ADX value above which market is STRONG_TREND (default: 30)
    """

    def __init__(
        self,
        period: int = 14,
        trending_threshold: float = 25.0,
        weak_trend_threshold: float = 20.0,
        strong_trend_threshold: float = 30.0
    ):
        """
        Initialize ADX calculator with configurable thresholds

        Args:
            period: Lookback period for ADX calculation (default: 14)
            trending_threshold: ADX >= this value = TRENDING (default: 25)
            weak_trend_threshold: ADX >= this and < trending = WEAK_TREND (default: 20)
            strong_trend_threshold: ADX >= this = STRONG_TREND (default: 30)
        """
        # Validate period
        if period < 2:
            raise ValueError("ADX period must be at least 2")

        self.period = period
        self.trending_threshold = trending_threshold
        self.weak_trend_threshold = weak_trend_threshold
        self.strong_trend_threshold = strong_trend_threshold

        logger.info(
            f"ADXCalculator initialized: period={period}, "
            f"thresholds=[weak:{weak_trend_threshold}, trend:{trending_threshold}, strong:{strong_trend_threshold}]"
        )

    def calculate(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Dict:
        """
        Calculate ADX, +DI, -DI and market regime classification

        Args:
            highs: List of high prices (oldest to newest)
            lows: List of low prices (oldest to newest)
            closes: List of close prices (oldest to newest)

        Returns:
            Dictionary containing:
            - adx: Current ADX value (0-100)
            - plus_di: Current +DI value (0-100)
            - minus_di: Current -DI value (0-100)
            - dx: Current DX value (0-100)
            - regime: Market regime classification (TRENDING/RANGING/WEAK_TREND/STRONG_TREND)
            - direction: Trend direction (BULLISH/BEARISH/NEUTRAL)
            - confidence: Confidence score for regime classification (0.0-1.0)
            - description: Human-readable description
            - timestamp: Calculation timestamp in milliseconds
        """
        # Validate input data length
        min_required = self.period * 2 + 1  # Need enough data for smoothing
        if len(highs) < min_required or len(lows) < min_required or len(closes) < min_required:
            logger.warning(
                f"Insufficient data for ADX: need {min_required} candles, "
                f"got {len(closes)}"
            )
            return self._default_response()

        try:
            # Create DataFrame for calculations
            df = pd.DataFrame({
                'high': highs,
                'low': lows,
                'close': closes
            })

            # Step 1: Calculate True Range (TR)
            # TR = max(high - low, |high - prev_close|, |low - prev_close|)
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

            # Step 2: Calculate Directional Movement (+DM and -DM)
            # +DM = high - prev_high (if positive and greater than -DM)
            # -DM = prev_low - low (if positive and greater than +DM)
            df['prev_high'] = df['high'].shift(1)
            df['prev_low'] = df['low'].shift(1)

            df['plus_dm'] = df['high'] - df['prev_high']
            df['minus_dm'] = df['prev_low'] - df['low']

            # Apply +DM/-DM rules
            df.loc[(df['plus_dm'] < 0), 'plus_dm'] = 0
            df.loc[(df['minus_dm'] < 0), 'minus_dm'] = 0
            df.loc[(df['plus_dm'] < df['minus_dm']), 'plus_dm'] = 0
            df.loc[(df['minus_dm'] < df['plus_dm']), 'minus_dm'] = 0
            df.loc[(df['plus_dm'] == df['minus_dm']), ['plus_dm', 'minus_dm']] = 0

            # Step 3: Apply Wilder's smoothing (exponential moving average variant)
            # Wilder's smoothing: SMA for first period, then: prev + (new - prev)/period
            alpha = 1.0 / self.period

            df['smoothed_tr'] = df['tr'].ewm(alpha=alpha, adjust=False).mean()
            df['smoothed_plus_dm'] = df['plus_dm'].ewm(alpha=alpha, adjust=False).mean()
            df['smoothed_minus_dm'] = df['minus_dm'].ewm(alpha=alpha, adjust=False).mean()

            # Step 4: Calculate +DI and -DI
            # +DI = 100 * smoothed(+DM) / smoothed(TR)
            # -DI = 100 * smoothed(-DM) / smoothed(TR)
            df['plus_di'] = 100 * df['smoothed_plus_dm'] / df['smoothed_tr']
            df['minus_di'] = 100 * df['smoothed_minus_dm'] / df['smoothed_tr']

            # Handle division by zero
            df['plus_di'] = df['plus_di'].replace([np.inf, -np.inf], 0).fillna(0)
            df['minus_di'] = df['minus_di'].replace([np.inf, -np.inf], 0).fillna(0)

            # Step 5: Calculate DX (Directional Movement Index)
            # DX = 100 * |+DI - -DI| / (+DI + -DI)
            df['di_diff'] = abs(df['plus_di'] - df['minus_di'])
            df['di_sum'] = df['plus_di'] + df['minus_di']
            df['dx'] = 100 * df['di_diff'] / df['di_sum']
            df['dx'] = df['dx'].replace([np.inf, -np.inf], 0).fillna(0)

            # Step 6: Calculate ADX (smoothed DX)
            df['adx'] = df['dx'].ewm(alpha=alpha, adjust=False).mean()

            # Get latest values
            adx = float(df['adx'].iloc[-1])
            plus_di = float(df['plus_di'].iloc[-1])
            minus_di = float(df['minus_di'].iloc[-1])
            dx = float(df['dx'].iloc[-1])

            # Classify market regime
            regime = self._classify_regime(adx)

            # Determine trend direction
            direction = self._determine_direction(plus_di, minus_di)

            # Calculate confidence based on ADX clarity
            confidence = self._calculate_confidence(adx, plus_di, minus_di)

            # Build description
            description = self._build_description(adx, regime, direction, plus_di, minus_di)

            logger.info(
                f"ADX calculated: ADX={adx:.2f}, +DI={plus_di:.2f}, -DI={minus_di:.2f}, "
                f"regime={regime.value}, direction={direction.value}"
            )

            return {
                "adx": round(adx, 2),
                "plus_di": round(plus_di, 2),
                "minus_di": round(minus_di, 2),
                "dx": round(dx, 2),
                "regime": regime.value,
                "direction": direction.value,
                "confidence": round(confidence, 2),
                "description": description,
                "thresholds": {
                    "weak_trend": self.weak_trend_threshold,
                    "trending": self.trending_threshold,
                    "strong_trend": self.strong_trend_threshold
                },
                "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
            }

        except Exception as e:
            logger.error(f"Error calculating ADX: {e}", exc_info=True)
            return self._default_response()

    def _classify_regime(self, adx: float) -> MarketRegime:
        """
        Classify market regime based on ADX value

        Args:
            adx: Current ADX value

        Returns:
            MarketRegime enum value
        """
        if adx >= self.strong_trend_threshold:
            return MarketRegime.STRONG_TREND
        elif adx >= self.trending_threshold:
            return MarketRegime.TRENDING
        elif adx >= self.weak_trend_threshold:
            return MarketRegime.WEAK_TREND
        else:
            return MarketRegime.RANGING

    def _determine_direction(self, plus_di: float, minus_di: float) -> TrendDirection:
        """
        Determine trend direction based on +DI and -DI comparison

        Args:
            plus_di: Positive directional indicator value
            minus_di: Negative directional indicator value

        Returns:
            TrendDirection enum value
        """
        # Consider a 10% difference threshold for neutral classification
        di_diff_pct = abs(plus_di - minus_di) / max(plus_di + minus_di, 1) * 100

        if di_diff_pct < 10:  # DIs are approximately equal
            return TrendDirection.NEUTRAL
        elif plus_di > minus_di:
            return TrendDirection.BULLISH
        else:
            return TrendDirection.BEARISH

    def _calculate_confidence(self, adx: float, plus_di: float, minus_di: float) -> float:
        """
        Calculate confidence score for the regime classification

        Higher confidence when:
        - ADX is far from threshold boundaries
        - +DI and -DI have clear separation

        Args:
            adx: Current ADX value
            plus_di: Positive directional indicator
            minus_di: Negative directional indicator

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence from ADX strength (normalized 0-50 scale)
        adx_confidence = min(adx / 50, 1.0)

        # DI separation confidence
        di_sum = plus_di + minus_di
        if di_sum > 0:
            di_separation = abs(plus_di - minus_di) / di_sum
        else:
            di_separation = 0

        # Combined confidence (weighted average)
        confidence = (adx_confidence * 0.6) + (di_separation * 0.4)

        return min(max(confidence, 0.0), 1.0)

    def _build_description(
        self,
        adx: float,
        regime: MarketRegime,
        direction: TrendDirection,
        plus_di: float,
        minus_di: float
    ) -> str:
        """
        Build human-readable description of the ADX analysis

        Args:
            adx: Current ADX value
            regime: Market regime classification
            direction: Trend direction
            plus_di: Positive directional indicator
            minus_di: Negative directional indicator

        Returns:
            Description string
        """
        # Regime description
        regime_desc = {
            MarketRegime.STRONG_TREND: "Strong trending market",
            MarketRegime.TRENDING: "Trending market",
            MarketRegime.WEAK_TREND: "Weak trend developing",
            MarketRegime.RANGING: "Ranging/sideways market"
        }

        # Direction description
        direction_desc = {
            TrendDirection.BULLISH: "bullish bias",
            TrendDirection.BEARISH: "bearish bias",
            TrendDirection.NEUTRAL: "no clear directional bias"
        }

        return (
            f"{regime_desc[regime]} (ADX: {adx:.1f}) with {direction_desc[direction]} "
            f"(+DI: {plus_di:.1f}, -DI: {minus_di:.1f})"
        )

    def _default_response(self) -> Dict:
        """
        Return default ADX response when calculation fails

        Returns:
            Dictionary with default/neutral values
        """
        return {
            "adx": 0.0,
            "plus_di": 0.0,
            "minus_di": 0.0,
            "dx": 0.0,
            "regime": MarketRegime.RANGING.value,
            "direction": TrendDirection.NEUTRAL.value,
            "confidence": 0.0,
            "description": "Insufficient data for ADX calculation",
            "thresholds": {
                "weak_trend": self.weak_trend_threshold,
                "trending": self.trending_threshold,
                "strong_trend": self.strong_trend_threshold
            },
            "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
        }

    def calculate_with_signal(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Tuple[Dict, str, float]:
        """
        Calculate ADX and generate trading signal based on regime

        This is a convenience method for integration with the trading system.

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices

        Returns:
            Tuple of (adx_data, signal, confidence) where:
            - adx_data: Full ADX calculation result
            - signal: "BUY", "SELL", or "HOLD"
            - confidence: Signal confidence (0.0-1.0)
        """
        adx_data = self.calculate(highs, lows, closes)

        regime = adx_data["regime"]
        direction = adx_data["direction"]
        adx = adx_data["adx"]

        # Generate signal based on regime and direction
        # In strong trends, follow the direction
        # In ranging markets, look for reversal opportunities
        if regime in [MarketRegime.STRONG_TREND.value, MarketRegime.TRENDING.value]:
            if direction == TrendDirection.BULLISH.value:
                signal = "BUY"
                confidence = min(adx / 50, 0.9)  # Cap at 0.9
            elif direction == TrendDirection.BEARISH.value:
                signal = "SELL"
                confidence = min(adx / 50, 0.9)
            else:
                signal = "HOLD"
                confidence = 0.5
        else:
            # In ranging/weak trend markets, be cautious
            signal = "HOLD"
            confidence = 0.3

        return adx_data, signal, round(confidence, 2)
