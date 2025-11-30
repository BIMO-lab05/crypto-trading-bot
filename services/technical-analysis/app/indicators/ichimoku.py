"""
Ichimoku Cloud (Ichimoku Kinko Hyo) Calculator
Purpose: Calculate Ichimoku Cloud components and generate trading signals

The Ichimoku Cloud is a comprehensive indicator that defines support and resistance,
identifies trend direction, gauges momentum, and provides trading signals.

Components:
    - Tenkan-sen (Conversion Line): 9-period high+low / 2
    - Kijun-sen (Base Line): 26-period high+low / 2
    - Senkou Span A (Leading Span A): (Tenkan + Kijun) / 2, projected 26 periods ahead
    - Senkou Span B (Leading Span B): 52-period high+low / 2, projected 26 periods ahead
    - Chikou Span (Lagging Span): Close price projected 26 periods back

Signal Logic:
    - BUY: Price above cloud + TK cross bullish + Chikou above price
    - SELL: Price below cloud + TK cross bearish + Chikou below price
    - HOLD: Price inside cloud or mixed signals
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple, Dict, Any
from app.models import SignalType

# Configure logger for this module
logger = logging.getLogger(__name__)


class IchimokuCalculator:
    """
    Calculate Ichimoku Cloud (Ichimoku Kinko Hyo)

    Ichimoku is a momentum indicator that defines support/resistance levels
    with dynamic clouds, trend direction, and trading signals.

    Standard periods:
        - Tenkan-sen (Conversion): 9 periods
        - Kijun-sen (Base): 26 periods
        - Senkou Span B: 52 periods
        - Displacement (projection): 26 periods

    Attributes:
        tenkan_period: Period for Tenkan-sen calculation (default: 9)
        kijun_period: Period for Kijun-sen calculation (default: 26)
        senkou_b_period: Period for Senkou Span B calculation (default: 52)
        displacement: Number of periods to project spans (default: 26)
    """

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
        displacement: int = 26
    ):
        """
        Initialize Ichimoku calculator with configurable periods

        Args:
            tenkan_period: Period for Tenkan-sen (Conversion Line), default 9
            kijun_period: Period for Kijun-sen (Base Line), default 26
            senkou_b_period: Period for Senkou Span B, default 52
            displacement: Periods to project Senkou spans ahead, default 26
        """
        # Store configuration parameters
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_b_period = senkou_b_period
        self.displacement = displacement

        # Calculate minimum required periods for calculation
        # Need at least senkou_b_period + displacement for full cloud projection
        self.min_periods = senkou_b_period + displacement

        # Log initialization with parameters
        logger.info(
            f"Ichimoku Calculator initialized: "
            f"tenkan={tenkan_period}, kijun={kijun_period}, "
            f"senkou_b={senkou_b_period}, displacement={displacement}"
        )

    def _calculate_midpoint(
        self,
        df: pd.DataFrame,
        period: int
    ) -> pd.Series:
        """
        Calculate (highest high + lowest low) / 2 for a given period

        This is the core calculation for Tenkan-sen, Kijun-sen, and Senkou Span B.
        Uses rolling window to find period high/low and calculates midpoint.

        Args:
            df: DataFrame with 'high' and 'low' columns
            period: Number of periods for the calculation

        Returns:
            Series with midpoint values
        """
        # Get rolling highest high over the period
        period_high = df['high'].rolling(window=period).max()

        # Get rolling lowest low over the period
        period_low = df['low'].rolling(window=period).min()

        # Calculate midpoint: (highest + lowest) / 2
        midpoint = (period_high + period_low) / 2

        return midpoint

    def calculate(self, df: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        Calculate all Ichimoku Cloud components

        Calculates current values for all five Ichimoku components:
        - Tenkan-sen (Conversion Line)
        - Kijun-sen (Base Line)
        - Senkou Span A (Leading Span A)
        - Senkou Span B (Leading Span B)
        - Chikou Span (Lagging Span)

        Args:
            df: DataFrame with 'open', 'high', 'low', 'close' columns

        Returns:
            Dict containing all component values, cloud bounds, and price position,
            or None if insufficient data
        """
        # Validate minimum data requirements
        if len(df) < self.min_periods:
            logger.warning(
                f"Insufficient data for Ichimoku: need {self.min_periods}, got {len(df)}"
            )
            return None

        try:
            # ===== Calculate Tenkan-sen (Conversion Line) =====
            # Formula: (9-period high + 9-period low) / 2
            # Faster moving line, represents short-term equilibrium
            tenkan_sen = self._calculate_midpoint(df, self.tenkan_period)

            # ===== Calculate Kijun-sen (Base Line) =====
            # Formula: (26-period high + 26-period low) / 2
            # Slower moving line, represents medium-term equilibrium
            kijun_sen = self._calculate_midpoint(df, self.kijun_period)

            # ===== Calculate Senkou Span A (Leading Span A) =====
            # Formula: (Tenkan-sen + Kijun-sen) / 2, projected 26 periods ahead
            # Forms one edge of the cloud (kumo)
            senkou_span_a = (tenkan_sen + kijun_sen) / 2

            # ===== Calculate Senkou Span B (Leading Span B) =====
            # Formula: (52-period high + 52-period low) / 2, projected 26 periods ahead
            # Forms the other edge of the cloud (kumo)
            senkou_span_b = self._calculate_midpoint(df, self.senkou_b_period)

            # ===== Get current values =====
            # Current price is the most recent close
            current_price = float(df['close'].iloc[-1])

            # Current Tenkan-sen value
            current_tenkan = float(tenkan_sen.iloc[-1])

            # Current Kijun-sen value
            current_kijun = float(kijun_sen.iloc[-1])

            # Senkou Span values at current position (these represent future cloud)
            # For current cloud, we look back by displacement periods
            cloud_index = -self.displacement if len(df) > self.displacement else 0
            current_span_a = float(senkou_span_a.iloc[cloud_index])
            current_span_b = float(senkou_span_b.iloc[cloud_index])

            # ===== Calculate Chikou Span (Lagging Span) =====
            # Formula: Current close, plotted 26 periods back
            # We compare it to the price 26 periods ago
            chikou_span = float(df['close'].iloc[-1])  # Current close value

            # Price 26 periods ago for Chikou comparison
            chikou_comparison_idx = -self.displacement - 1
            if abs(chikou_comparison_idx) < len(df):
                chikou_comparison_price = float(df['close'].iloc[chikou_comparison_idx])
            else:
                chikou_comparison_price = current_price

            # ===== Determine cloud boundaries =====
            # Cloud upper bound is the higher of Span A and Span B
            cloud_top = max(current_span_a, current_span_b)

            # Cloud lower bound is the lower of Span A and Span B
            cloud_bottom = min(current_span_a, current_span_b)

            # Cloud thickness (volatility indicator)
            cloud_thickness = abs(current_span_a - current_span_b)

            # ===== Determine cloud color (trend indicator) =====
            # Green cloud: Span A > Span B (bullish)
            # Red cloud: Span B > Span A (bearish)
            cloud_color = "green" if current_span_a > current_span_b else "red"

            # ===== Determine price position relative to cloud =====
            if current_price > cloud_top:
                price_position = "above_cloud"  # Bullish zone
            elif current_price < cloud_bottom:
                price_position = "below_cloud"  # Bearish zone
            else:
                price_position = "inside_cloud"  # Consolidation/indecision

            # ===== Build result dictionary with all components =====
            result = {
                # Core Ichimoku components
                "tenkan_sen": current_tenkan,
                "kijun_sen": current_kijun,
                "senkou_span_a": current_span_a,
                "senkou_span_b": current_span_b,
                "chikou_span": chikou_span,

                # Current price for reference
                "current_price": current_price,

                # Cloud analysis
                "cloud_top": cloud_top,
                "cloud_bottom": cloud_bottom,
                "cloud_thickness": cloud_thickness,
                "cloud_color": cloud_color,

                # Position analysis
                "price_position": price_position,
                "chikou_comparison_price": chikou_comparison_price,

                # TK cross status
                "tk_cross": "bullish" if current_tenkan > current_kijun else "bearish",
                "tk_distance": current_tenkan - current_kijun
            }

            logger.debug(f"Calculated Ichimoku: price={current_price:.2f}, position={price_position}")
            return result

        except Exception as e:
            logger.error(f"Error calculating Ichimoku: {e}", exc_info=True)
            return None

    def generate_signal(
        self,
        ichimoku_data: Dict[str, Any]
    ) -> Tuple[SignalType, float]:
        """
        Generate trading signal based on Ichimoku Cloud analysis

        Signal logic combines multiple Ichimoku signals:
        - Price position relative to cloud (trend)
        - Tenkan-sen/Kijun-sen cross (momentum)
        - Chikou Span position (confirmation)

        Strong BUY conditions:
            - Price above cloud
            - Tenkan-sen above Kijun-sen (bullish TK cross)
            - Chikou Span above price 26 periods ago

        Strong SELL conditions:
            - Price below cloud
            - Tenkan-sen below Kijun-sen (bearish TK cross)
            - Chikou Span below price 26 periods ago

        HOLD conditions:
            - Price inside cloud (consolidation)
            - Mixed signals from different components

        Args:
            ichimoku_data: Dict with Ichimoku component values

        Returns:
            Tuple of (SignalType, confidence) where confidence is 0.0 to 1.0
        """
        # Extract key values from ichimoku data
        current_price = ichimoku_data["current_price"]
        tenkan = ichimoku_data["tenkan_sen"]
        kijun = ichimoku_data["kijun_sen"]
        chikou = ichimoku_data["chikou_span"]
        chikou_price = ichimoku_data["chikou_comparison_price"]
        price_position = ichimoku_data["price_position"]
        cloud_color = ichimoku_data["cloud_color"]
        cloud_thickness = ichimoku_data["cloud_thickness"]

        # ===== Evaluate individual signal components =====

        # Signal 1: Price position relative to cloud
        # Above cloud = bullish (+1), Below cloud = bearish (-1), Inside = neutral (0)
        if price_position == "above_cloud":
            position_signal = 1
        elif price_position == "below_cloud":
            position_signal = -1
        else:
            position_signal = 0

        # Signal 2: Tenkan-Kijun cross (TK cross)
        # Tenkan > Kijun = bullish (+1), Tenkan < Kijun = bearish (-1)
        tk_signal = 1 if tenkan > kijun else -1

        # Signal 3: Chikou Span position
        # Chikou above price 26 periods ago = bullish (+1)
        # Chikou below price 26 periods ago = bearish (-1)
        chikou_signal = 1 if chikou > chikou_price else -1

        # Signal 4: Cloud color (future trend indicator)
        # Green cloud = bullish (+0.5), Red cloud = bearish (-0.5)
        cloud_signal = 0.5 if cloud_color == "green" else -0.5

        # Signal 5: Price relative to Kijun-sen (equilibrium)
        # Price > Kijun = bullish (+0.5), Price < Kijun = bearish (-0.5)
        kijun_signal = 0.5 if current_price > kijun else -0.5

        # ===== Calculate composite signal score =====
        # Weight the signals: position (2x), TK cross (1.5x), Chikou (1x), cloud (0.5x), kijun (0.5x)
        total_score = (
            position_signal * 2.0 +    # Position is most important
            tk_signal * 1.5 +          # TK cross is second most important
            chikou_signal * 1.0 +      # Chikou confirmation
            cloud_signal * 0.5 +       # Cloud color
            kijun_signal * 0.5         # Price-Kijun relationship
        )

        # Maximum possible score is: 2 + 1.5 + 1 + 0.5 + 0.5 = 5.5
        max_score = 5.5

        # ===== Determine signal based on composite score =====
        if price_position == "inside_cloud":
            # Inside cloud = indecision, default to HOLD
            signal = SignalType.HOLD
            # Confidence based on how close to cloud edges
            cloud_top = ichimoku_data["cloud_top"]
            cloud_bottom = ichimoku_data["cloud_bottom"]
            cloud_range = cloud_top - cloud_bottom

            if cloud_range > 0:
                # Position within cloud (0 = bottom, 1 = top)
                cloud_pos = (current_price - cloud_bottom) / cloud_range
                # Lower confidence in middle, higher near edges
                confidence = abs(cloud_pos - 0.5) * 0.6 + 0.2
            else:
                confidence = 0.3

            logger.info(
                f"Ichimoku: Price inside cloud -> HOLD "
                f"(score: {total_score:.2f}, confidence: {confidence:.2f})"
            )

        elif total_score >= 3.0:
            # Strong bullish signal: multiple confirmations
            signal = SignalType.BUY
            # Confidence based on score strength
            confidence = min(1.0, (total_score / max_score) + 0.2)

            logger.info(
                f"Ichimoku: Strong BUY signal "
                f"(score: {total_score:.2f}, confidence: {confidence:.2f})"
            )

        elif total_score <= -3.0:
            # Strong bearish signal: multiple confirmations
            signal = SignalType.SELL
            # Confidence based on absolute score strength
            confidence = min(1.0, (abs(total_score) / max_score) + 0.2)

            logger.info(
                f"Ichimoku: Strong SELL signal "
                f"(score: {total_score:.2f}, confidence: {confidence:.2f})"
            )

        elif total_score >= 1.5:
            # Moderate bullish signal
            signal = SignalType.BUY
            confidence = 0.5 + (total_score - 1.5) / (3.0 - 1.5) * 0.3

            logger.info(
                f"Ichimoku: Moderate BUY signal "
                f"(score: {total_score:.2f}, confidence: {confidence:.2f})"
            )

        elif total_score <= -1.5:
            # Moderate bearish signal
            signal = SignalType.SELL
            confidence = 0.5 + (abs(total_score) - 1.5) / (3.0 - 1.5) * 0.3

            logger.info(
                f"Ichimoku: Moderate SELL signal "
                f"(score: {total_score:.2f}, confidence: {confidence:.2f})"
            )

        else:
            # Mixed signals, default to HOLD
            signal = SignalType.HOLD
            confidence = 0.3 + abs(total_score) / 3.0 * 0.2

            logger.debug(
                f"Ichimoku: Mixed signals -> HOLD "
                f"(score: {total_score:.2f})"
            )

        # ===== Adjust confidence based on cloud thickness =====
        # Thicker cloud = stronger support/resistance = higher confidence
        # Thin cloud = weaker levels = lower confidence
        if cloud_thickness > 0:
            # Normalize thickness relative to price (percentage)
            thickness_ratio = cloud_thickness / ichimoku_data["current_price"]

            if thickness_ratio < 0.005:  # Very thin cloud (<0.5%)
                confidence *= 0.8
                logger.debug("Thin cloud detected, reducing confidence by 20%")
            elif thickness_ratio > 0.02:  # Thick cloud (>2%)
                confidence *= 1.1
                logger.debug("Thick cloud detected, boosting confidence by 10%")

        # Ensure confidence stays within bounds
        confidence = max(0.1, min(1.0, confidence))

        return signal, round(confidence, 2)

    def detect_tk_cross(
        self,
        df: pd.DataFrame,
        lookback: int = 5
    ) -> Optional[str]:
        """
        Detect Tenkan-sen/Kijun-sen crossover in recent periods

        TK Cross is a key Ichimoku signal:
        - Bullish cross: Tenkan crosses above Kijun (buy signal)
        - Bearish cross: Tenkan crosses below Kijun (sell signal)

        Args:
            df: DataFrame with OHLC data
            lookback: Number of periods to check for crossover

        Returns:
            "bullish" for Tenkan crossing above Kijun
            "bearish" for Tenkan crossing below Kijun
            None if no crossover detected in lookback period
        """
        # Validate data requirements
        if len(df) < max(self.tenkan_period, self.kijun_period) + lookback:
            return None

        try:
            # Calculate Tenkan-sen and Kijun-sen series
            tenkan_sen = self._calculate_midpoint(df, self.tenkan_period)
            kijun_sen = self._calculate_midpoint(df, self.kijun_period)

            # Calculate TK difference for recent periods
            tk_diff = tenkan_sen - kijun_sen
            recent_diff = tk_diff.tail(lookback).values

            # Check for bullish crossover (TK diff goes from negative to positive)
            if recent_diff[-1] > 0 and any(d < 0 for d in recent_diff[:-1]):
                logger.info("Detected bullish Tenkan-Kijun crossover")
                return "bullish"

            # Check for bearish crossover (TK diff goes from positive to negative)
            if recent_diff[-1] < 0 and any(d > 0 for d in recent_diff[:-1]):
                logger.info("Detected bearish Tenkan-Kijun crossover")
                return "bearish"

            return None

        except Exception as e:
            logger.error(f"Error detecting TK crossover: {e}", exc_info=True)
            return None

    def detect_kumo_breakout(
        self,
        df: pd.DataFrame,
        lookback: int = 5
    ) -> Optional[str]:
        """
        Detect cloud (kumo) breakout in recent periods

        Kumo breakout is a strong trend signal:
        - Bullish breakout: Price breaks above cloud
        - Bearish breakout: Price breaks below cloud

        Args:
            df: DataFrame with OHLC data
            lookback: Number of periods to check for breakout

        Returns:
            "bullish" for price breaking above cloud
            "bearish" for price breaking below cloud
            None if no breakout detected
        """
        if len(df) < self.min_periods + lookback:
            return None

        try:
            # Calculate cloud boundaries for recent periods
            senkou_a = (
                self._calculate_midpoint(df, self.tenkan_period) +
                self._calculate_midpoint(df, self.kijun_period)
            ) / 2
            senkou_b = self._calculate_midpoint(df, self.senkou_b_period)

            # Get recent close prices
            recent_close = df['close'].tail(lookback).values

            # Get cloud bounds (shifted back by displacement for current cloud)
            recent_span_a = senkou_a.shift(self.displacement).tail(lookback).values
            recent_span_b = senkou_b.shift(self.displacement).tail(lookback).values

            # Calculate cloud top and bottom for each period
            cloud_tops = np.maximum(recent_span_a, recent_span_b)
            cloud_bottoms = np.minimum(recent_span_a, recent_span_b)

            # Check for bullish breakout (price moves from inside/below to above cloud)
            current_above = recent_close[-1] > cloud_tops[-1]
            was_below_or_inside = any(
                c <= ct for c, ct in zip(recent_close[:-1], cloud_tops[:-1])
            )
            if current_above and was_below_or_inside:
                logger.info("Detected bullish kumo breakout")
                return "bullish"

            # Check for bearish breakout (price moves from inside/above to below cloud)
            current_below = recent_close[-1] < cloud_bottoms[-1]
            was_above_or_inside = any(
                c >= cb for c, cb in zip(recent_close[:-1], cloud_bottoms[:-1])
            )
            if current_below and was_above_or_inside:
                logger.info("Detected bearish kumo breakout")
                return "bearish"

            return None

        except Exception as e:
            logger.error(f"Error detecting kumo breakout: {e}", exc_info=True)
            return None

    def calculate_with_signal(
        self,
        df: pd.DataFrame
    ) -> Tuple[Optional[Dict[str, Any]], SignalType, float]:
        """
        Calculate Ichimoku components and generate signal in one call

        This is the primary method for getting both Ichimoku values and
        trading signal with a single calculation pass.

        Args:
            df: DataFrame with 'open', 'high', 'low', 'close' columns

        Returns:
            Tuple of (ichimoku_dict, signal, confidence)
            - ichimoku_dict: All component values or None if calculation failed
            - signal: SignalType (BUY, SELL, HOLD, NEUTRAL)
            - confidence: Float from 0.0 to 1.0
        """
        # Calculate all Ichimoku components
        ichimoku_data = self.calculate(df)

        # Return neutral if calculation failed
        if ichimoku_data is None:
            return None, SignalType.NEUTRAL, 0.0

        # Generate base signal from Ichimoku analysis
        signal, confidence = self.generate_signal(ichimoku_data)

        # ===== Boost confidence for recent crossovers/breakouts =====

        # Check for TK crossover (momentum confirmation)
        tk_cross = self.detect_tk_cross(df)
        if tk_cross:
            # Crossover confirms direction = boost confidence
            if (tk_cross == "bullish" and signal == SignalType.BUY) or \
               (tk_cross == "bearish" and signal == SignalType.SELL):
                confidence = min(1.0, confidence * 1.15)
                logger.info(f"TK crossover confirms signal, confidence boosted to {confidence:.2f}")

        # Check for kumo breakout (trend confirmation)
        kumo_break = self.detect_kumo_breakout(df)
        if kumo_break:
            # Breakout confirms direction = significant boost
            if (kumo_break == "bullish" and signal == SignalType.BUY) or \
               (kumo_break == "bearish" and signal == SignalType.SELL):
                confidence = min(1.0, confidence * 1.2)
                logger.info(f"Kumo breakout confirms signal, confidence boosted to {confidence:.2f}")

        return ichimoku_data, signal, round(confidence, 2)

    def calculate_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Ichimoku series for entire DataFrame (for backtesting/charting)

        Returns a DataFrame with all Ichimoku components calculated for
        each row, useful for backtesting strategies or creating charts.

        Note: Senkou Spans are calculated at their natural positions,
        not shifted forward. Apply .shift(displacement) for actual
        cloud plotting.

        Args:
            df: DataFrame with 'open', 'high', 'low', 'close' columns

        Returns:
            DataFrame with columns:
            - tenkan_sen: Conversion Line
            - kijun_sen: Base Line
            - senkou_span_a: Leading Span A (unshifted)
            - senkou_span_b: Leading Span B (unshifted)
            - chikou_span: Lagging Span (current close)
        """
        # Validate minimum data requirements
        if len(df) < self.senkou_b_period:
            logger.warning("Insufficient data for Ichimoku series calculation")
            return pd.DataFrame()

        try:
            # Calculate Tenkan-sen (Conversion Line)
            tenkan_sen = self._calculate_midpoint(df, self.tenkan_period)

            # Calculate Kijun-sen (Base Line)
            kijun_sen = self._calculate_midpoint(df, self.kijun_period)

            # Calculate Senkou Span A (Leading Span A)
            senkou_span_a = (tenkan_sen + kijun_sen) / 2

            # Calculate Senkou Span B (Leading Span B)
            senkou_span_b = self._calculate_midpoint(df, self.senkou_b_period)

            # Chikou Span is simply the close price (plotted 26 periods back)
            chikou_span = df['close'].copy()

            # Build result DataFrame
            result_df = pd.DataFrame({
                'tenkan_sen': tenkan_sen,
                'kijun_sen': kijun_sen,
                'senkou_span_a': senkou_span_a,
                'senkou_span_b': senkou_span_b,
                'chikou_span': chikou_span,
                'cloud_top': pd.concat([senkou_span_a, senkou_span_b], axis=1).max(axis=1),
                'cloud_bottom': pd.concat([senkou_span_a, senkou_span_b], axis=1).min(axis=1)
            })

            logger.debug(f"Calculated Ichimoku series with {len(result_df)} rows")
            return result_df

        except Exception as e:
            logger.error(f"Error calculating Ichimoku series: {e}", exc_info=True)
            return pd.DataFrame()

    def get_cloud_forecast(
        self,
        df: pd.DataFrame,
        periods_ahead: int = 26
    ) -> Optional[Dict[str, Any]]:
        """
        Get cloud forecast for future periods

        Since Senkou Spans are projected ahead, we can see future
        support/resistance levels before price reaches them.

        Args:
            df: DataFrame with OHLC data
            periods_ahead: How many periods to forecast (max: displacement)

        Returns:
            Dict with future cloud levels and trend forecast, or None if error
        """
        if periods_ahead > self.displacement:
            periods_ahead = self.displacement
            logger.warning(f"Capped forecast to {self.displacement} periods")

        if len(df) < self.senkou_b_period:
            return None

        try:
            # Calculate current Senkou Spans (these project into future)
            tenkan_sen = self._calculate_midpoint(df, self.tenkan_period)
            kijun_sen = self._calculate_midpoint(df, self.kijun_period)
            senkou_a = (tenkan_sen + kijun_sen) / 2
            senkou_b = self._calculate_midpoint(df, self.senkou_b_period)

            # Get values that will form future cloud
            future_span_a = float(senkou_a.iloc[-1])
            future_span_b = float(senkou_b.iloc[-1])

            # Determine future cloud characteristics
            future_cloud_top = max(future_span_a, future_span_b)
            future_cloud_bottom = min(future_span_a, future_span_b)
            future_cloud_color = "green" if future_span_a > future_span_b else "red"

            forecast = {
                "periods_ahead": periods_ahead,
                "future_span_a": future_span_a,
                "future_span_b": future_span_b,
                "future_cloud_top": future_cloud_top,
                "future_cloud_bottom": future_cloud_bottom,
                "future_cloud_color": future_cloud_color,
                "future_cloud_thickness": future_cloud_top - future_cloud_bottom,
                "trend_forecast": "bullish" if future_cloud_color == "green" else "bearish"
            }

            logger.info(f"Cloud forecast: {future_cloud_color} cloud at {future_cloud_top:.2f}/{future_cloud_bottom:.2f}")
            return forecast

        except Exception as e:
            logger.error(f"Error calculating cloud forecast: {e}", exc_info=True)
            return None
