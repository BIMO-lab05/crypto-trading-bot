"""
Enhanced Squeeze Momentum (SQZMOM) Indicator
Purpose: Advanced squeeze detection with momentum analysis and acceleration tracking

This enhanced version of the Squeeze Momentum Indicator provides:
1. Bollinger Band squeeze detection (BB inside Keltner Channel)
2. Momentum histogram calculation using linear regression
3. Squeeze "firing" detection (release from squeeze state)
4. Momentum direction and acceleration tracking
5. Configurable squeeze duration tracking for confidence scoring

Signal Logic:
- BUY: Squeeze fires + momentum positive + momentum increasing
- SELL: Squeeze fires + momentum negative + momentum decreasing
- HOLD: Still in squeeze OR momentum flat

Author: Technical Analysis Service
Date: 2025-11-26
Version: 2.0 - Enhanced
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass
from enum import Enum
from scipy import stats
from app.models import SignalType

# Configure module logger
logger = logging.getLogger(__name__)


class SqueezeState(str, Enum):
    """
    Enumeration of possible squeeze states

    SQUEEZE_ON: Bollinger Bands are inside Keltner Channels (low volatility compression)
    SQUEEZE_OFF: Bollinger Bands are outside Keltner Channels (breakout released)
    SQUEEZE_FIRING: Transition from SQUEEZE_ON to SQUEEZE_OFF (breakout moment)
    NO_SQUEEZE: Neutral state (BB and KC partially overlapping)
    """
    SQUEEZE_ON = "SQUEEZE_ON"       # BB inside KC - compression active
    SQUEEZE_OFF = "SQUEEZE_OFF"     # BB outside KC - breakout released
    SQUEEZE_FIRING = "SQUEEZE_FIRING"  # Just released from squeeze
    NO_SQUEEZE = "NO_SQUEEZE"       # Transitional/neutral state


class MomentumDirection(str, Enum):
    """
    Enumeration of momentum direction states

    BULLISH_INCREASING: Positive momentum, accelerating upward
    BULLISH_DECREASING: Positive momentum, decelerating
    BEARISH_INCREASING: Negative momentum, accelerating downward (more negative)
    BEARISH_DECREASING: Negative momentum, decelerating (less negative)
    FLAT: Momentum near zero or unchanged
    """
    BULLISH_INCREASING = "BULLISH_INCREASING"   # Positive and growing (lime)
    BULLISH_DECREASING = "BULLISH_DECREASING"   # Positive but fading (green)
    BEARISH_INCREASING = "BEARISH_INCREASING"   # Negative and growing (red)
    BEARISH_DECREASING = "BEARISH_DECREASING"   # Negative but fading (maroon)
    FLAT = "FLAT"                               # Near zero change


@dataclass
class SqueezeMetadata:
    """
    Comprehensive metadata for squeeze momentum analysis

    Contains all relevant information about the current squeeze state,
    momentum values, histogram data, and band positions for detailed analysis.
    """
    # Squeeze state information
    squeeze_state: SqueezeState         # Current squeeze state
    squeeze_on: bool                    # Is squeeze currently active
    squeeze_off: bool                   # Is squeeze currently released
    squeeze_firing: bool                # Did squeeze just fire (transition)
    squeeze_duration: int               # Number of bars in current squeeze

    # Momentum information
    momentum_value: float               # Current momentum histogram value
    momentum_direction: MomentumDirection  # Direction classification
    momentum_acceleration: float        # Rate of momentum change
    momentum_strength: float            # Normalized momentum strength (0-1)

    # Histogram values (for visualization)
    histogram: List[float]              # Recent histogram values
    histogram_color: str                # Signal color (lime/green/red/maroon)

    # Band values
    bb_upper: float                     # Bollinger Band upper
    bb_basis: float                     # Bollinger Band middle (SMA)
    bb_lower: float                     # Bollinger Band lower
    kc_upper: float                     # Keltner Channel upper
    kc_basis: float                     # Keltner Channel middle
    kc_lower: float                     # Keltner Channel lower

    # Additional analytics
    current_price: float                # Current close price
    band_width_ratio: float             # BB width / KC width ratio

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for JSON serialization"""
        return {
            "squeeze_state": self.squeeze_state.value,
            "squeeze_on": self.squeeze_on,
            "squeeze_off": self.squeeze_off,
            "squeeze_firing": self.squeeze_firing,
            "squeeze_duration": self.squeeze_duration,
            "momentum_value": round(self.momentum_value, 6),
            "momentum_direction": self.momentum_direction.value,
            "momentum_acceleration": round(self.momentum_acceleration, 6),
            "momentum_strength": round(self.momentum_strength, 4),  # non-price-round
            "histogram": [round(h, 6) for h in self.histogram[-10:]],  # Last 10 values
            "histogram_color": self.histogram_color,
            # Price-domain: 4dp is exactly ADA's tick and lossy below it.
            # Full precision here; quantization belongs at order time.
            "bb_upper": float(self.bb_upper),
            "bb_basis": float(self.bb_basis),
            "bb_lower": float(self.bb_lower),
            "kc_upper": float(self.kc_upper),
            "kc_basis": float(self.kc_basis),
            "kc_lower": float(self.kc_lower),
            "current_price": float(self.current_price),
            "band_width_ratio": round(self.band_width_ratio, 4)  # non-price-round
        }


class EnhancedSqueezeMomentum:
    """
    Enhanced Squeeze Momentum Indicator

    This class provides advanced squeeze momentum analysis with:
    - Configurable Bollinger Bands and Keltner Channel parameters
    - Momentum histogram using linear regression
    - Squeeze firing detection (transition from squeeze ON to OFF)
    - Momentum direction and acceleration tracking
    - Confidence scoring based on multiple factors

    Trading Strategy:
    The squeeze momentum indicator identifies periods of low volatility
    (squeeze) that often precede significant price moves (breakouts).
    When the squeeze "fires" (releases), the momentum direction indicates
    the likely breakout direction.

    Parameters:
        bb_length: Bollinger Bands period (default: 20)
        bb_mult: Bollinger Bands standard deviation multiplier (default: 2.0)
        kc_length: Keltner Channel period (default: 20)
        kc_mult: Keltner Channel ATR multiplier (default: 1.5)
        momentum_length: Linear regression period for momentum (default: 12)
        use_true_range: Use True Range for KC calculation (default: True)
    """

    def __init__(
        self,
        bb_length: int = 20,
        bb_mult: float = 2.0,
        kc_length: int = 20,
        kc_mult: float = 1.5,
        momentum_length: int = 12,
        use_true_range: bool = True
    ):
        """
        Initialize Enhanced Squeeze Momentum Indicator

        Args:
            bb_length: Bollinger Bands period for SMA and StdDev calculation
            bb_mult: Standard deviation multiplier for BB width
            kc_length: Keltner Channel period for MA and ATR calculation
            kc_mult: ATR multiplier for KC width
            momentum_length: Period for linear regression momentum calculation
            use_true_range: If True, use True Range; if False, use simple high-low

        Standard Configuration:
            - BB: 20-period SMA with 2.0 standard deviations
            - KC: 20-period SMA with 1.5 ATR
            - Momentum: 12-period linear regression

        When BB width < KC width, squeeze is ON (low volatility)
        When BB width > KC width, squeeze is OFF (volatility expanding)
        """
        # Store configuration parameters
        self.bb_length = bb_length          # Bollinger Bands period
        self.bb_mult = bb_mult              # BB standard deviation multiplier
        self.kc_length = kc_length          # Keltner Channel period
        self.kc_mult = kc_mult              # KC ATR multiplier
        self.momentum_length = momentum_length  # Linear regression period
        self.use_true_range = use_true_range    # True Range vs simple range

        # Internal state tracking
        self._squeeze_history: List[bool] = []  # Track squeeze states for duration
        self._last_squeeze_state: Optional[bool] = None  # Track previous squeeze state

        # Log initialization with all parameters
        logger.info(
            f"Enhanced Squeeze Momentum initialized: "
            f"BB({bb_length}, {bb_mult}), KC({kc_length}, {kc_mult}), "
            f"Momentum({momentum_length}), TrueRange={use_true_range}"
        )

    def _calculate_bollinger_bands(
        self,
        close: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands from close prices

        Args:
            close: Series of close prices

        Returns:
            Tuple of (upper_band, basis, lower_band) as pandas Series

        Formula:
            basis = SMA(close, bb_length)
            std_dev = StdDev(close, bb_length)
            upper_band = basis + (bb_mult * std_dev)
            lower_band = basis - (bb_mult * std_dev)

        Bollinger Bands measure volatility using standard deviation.
        When bands contract, volatility is low (potential squeeze).
        When bands expand, volatility is high (potential breakout).
        """
        # Calculate Simple Moving Average (basis/middle line)
        basis = close.rolling(window=self.bb_length).mean()

        # Calculate standard deviation over the same period
        std_dev = close.rolling(window=self.bb_length).std()

        # Calculate deviation amount (std_dev multiplied by bb_mult)
        deviation = self.bb_mult * std_dev

        # Calculate upper and lower bands
        upper_band = basis + deviation
        lower_band = basis - deviation

        # Debug logging for latest values
        if len(close) > 0:
            logger.debug(
                f"BB calculated: basis={basis.iloc[-1]:.4f}, "
                f"upper={upper_band.iloc[-1]:.4f}, lower={lower_band.iloc[-1]:.4f}, "
                f"width={deviation.iloc[-1] * 2:.4f}"
            )

        return upper_band, basis, lower_band

    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate True Range (TR) for Keltner Channel

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            Series of True Range values

        Formula:
            TR = max(
                high - low,                    # Current period range
                abs(high - prev_close),        # Gap up range
                abs(low - prev_close)          # Gap down range
            )

        True Range captures intraday volatility plus any gaps between
        the previous close and current high/low. This provides a more
        accurate measure of volatility than simple high-low range.
        """
        # Method 1: Current period's high minus low
        high_low = df['high'] - df['low']

        # Method 2: Absolute value of current high minus previous close (gap up)
        high_prev_close = (df['high'] - df['close'].shift(1)).abs()

        # Method 3: Absolute value of current low minus previous close (gap down)
        low_prev_close = (df['low'] - df['close'].shift(1)).abs()

        # True Range is the maximum of all three methods
        true_range = pd.concat(
            [high_low, high_prev_close, low_prev_close],
            axis=1
        ).max(axis=1)

        logger.debug(f"True Range calculated: current={true_range.iloc[-1]:.6f}")

        return true_range

    def _calculate_keltner_channels(
        self,
        df: pd.DataFrame
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Keltner Channels from OHLC data

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            Tuple of (upper_kc, basis, lower_kc) as pandas Series

        Formula:
            basis = SMA(close, kc_length)
            range = True Range if use_true_range else (high - low)
            atr = SMA(range, kc_length)
            upper_kc = basis + (kc_mult * atr)
            lower_kc = basis - (kc_mult * atr)

        Keltner Channels use ATR-based bands instead of standard deviation.
        ATR is less sensitive to price spikes than standard deviation,
        making KC more stable than Bollinger Bands.
        """
        # Calculate moving average (basis/middle line)
        basis = df['close'].rolling(window=self.kc_length).mean()

        # Calculate range based on configuration
        if self.use_true_range:
            # True Range includes gaps between sessions
            range_values = self._calculate_true_range(df)
        else:
            # Simple range: just high minus low
            range_values = df['high'] - df['low']

        # Calculate Average True Range (ATR)
        atr = range_values.rolling(window=self.kc_length).mean()

        # Calculate upper and lower Keltner Channels
        upper_kc = basis + (self.kc_mult * atr)
        lower_kc = basis - (self.kc_mult * atr)

        # Debug logging for latest values
        if len(df) > 0:
            logger.debug(
                f"KC calculated: basis={basis.iloc[-1]:.4f}, "
                f"upper={upper_kc.iloc[-1]:.4f}, lower={lower_kc.iloc[-1]:.4f}, "
                f"atr={atr.iloc[-1]:.6f}"
            )

        return upper_kc, basis, lower_kc

    def _calculate_momentum_histogram(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate momentum histogram using linear regression

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            Series of momentum histogram values

        Formula (from LazyBear Pine Script):
            highest_high = highest(high, kc_length)
            lowest_low = lowest(low, kc_length)
            hl_midpoint = avg(highest_high, lowest_low)
            close_sma = sma(close, kc_length)
            price_midpoint = avg(hl_midpoint, close_sma)
            deviation = close - price_midpoint
            momentum = linreg(deviation, momentum_length, 0)

        The momentum histogram measures how price deviates from its
        midpoint, smoothed using linear regression. Positive values
        indicate bullish momentum; negative values indicate bearish.
        """
        # Calculate highest high over the lookback period
        highest_high = df['high'].rolling(window=self.kc_length).max()

        # Calculate lowest low over the lookback period
        lowest_low = df['low'].rolling(window=self.kc_length).min()

        # Calculate high-low midpoint (average of highest high and lowest low)
        hl_midpoint = (highest_high + lowest_low) / 2

        # Calculate SMA of close prices
        close_sma = df['close'].rolling(window=self.kc_length).mean()

        # Calculate price midpoint (average of hl_midpoint and close_sma)
        price_midpoint = (hl_midpoint + close_sma) / 2

        # Calculate deviation from price midpoint
        deviation = df['close'] - price_midpoint

        # Apply linear regression smoothing to deviation
        momentum = self._rolling_linear_regression(deviation, self.momentum_length)

        logger.debug(f"Momentum histogram calculated: current={momentum.iloc[-1]:.6f}")

        return momentum

    def _rolling_linear_regression(self, series: pd.Series, period: int) -> pd.Series:
        """
        Calculate rolling linear regression fitted values

        Args:
            series: Input data series
            period: Regression window period

        Returns:
            Series of linear regression fitted values at offset 0

        For each rolling window of size 'period', this function:
        1. Fits a linear regression line: y = mx + b
        2. Returns the fitted value at the most recent point

        This is equivalent to Pine Script's linreg(source, length, 0).
        The linear regression smooths the data while preserving the trend.
        """
        def calculate_linreg_value(window_values: np.ndarray) -> float:
            """
            Calculate linear regression fitted value for a single window

            Args:
                window_values: NumPy array of values in the window

            Returns:
                Fitted value at the end of the window (most recent point)
            """
            # Check for sufficient data
            if len(window_values) < period:
                return np.nan

            # Create x values (0, 1, 2, ..., period-1)
            x_values = np.arange(len(window_values))

            # Remove any NaN values from consideration
            mask = ~np.isnan(window_values)
            if mask.sum() < 2:  # Need at least 2 points for regression
                return np.nan

            # Filter to non-NaN values
            x_clean = x_values[mask]
            y_clean = window_values[mask]

            try:
                # Perform linear regression using scipy.stats.linregress
                # Returns: slope, intercept, r_value, p_value, std_err
                slope, intercept, _, _, _ = stats.linregress(x_clean, y_clean)

                # Calculate fitted value at the most recent point
                # Most recent point is at x = period - 1
                fitted_value = slope * (len(window_values) - 1) + intercept

                return fitted_value

            except Exception as e:
                logger.warning(f"Linear regression calculation failed: {e}")
                return np.nan

        # Apply rolling linear regression to the series
        result = series.rolling(window=period).apply(
            calculate_linreg_value,
            raw=True
        )

        return result

    def _detect_squeeze_state(
        self,
        bb_upper: pd.Series,
        bb_lower: pd.Series,
        kc_upper: pd.Series,
        kc_lower: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Detect squeeze conditions from band positions

        Args:
            bb_upper: Bollinger Bands upper band
            bb_lower: Bollinger Bands lower band
            kc_upper: Keltner Channel upper band
            kc_lower: Keltner Channel lower band

        Returns:
            Tuple of (squeeze_on, squeeze_off, squeeze_firing) as boolean Series

        Squeeze Detection Logic:
        - SQUEEZE_ON: BB is entirely inside KC
          (BB lower > KC lower AND BB upper < KC upper)
        - SQUEEZE_OFF: BB is entirely outside KC
          (BB lower < KC lower AND BB upper > KC upper)
        - SQUEEZE_FIRING: Transition from SQUEEZE_ON to SQUEEZE_OFF

        The "firing" signal is the most important - it indicates a
        potential breakout as volatility expands from a compressed state.
        """
        # Squeeze ON: Bollinger Bands are contained within Keltner Channels
        # This indicates low volatility compression (potential energy building)
        squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

        # Squeeze OFF: Bollinger Bands extend beyond Keltner Channels
        # This indicates volatility expansion (breakout in progress)
        squeeze_off = (bb_lower < kc_lower) & (bb_upper > kc_upper)

        # Squeeze FIRING: The critical transition from ON to OFF
        # Shift squeeze_on by 1 to get previous state. fill_value=False keeps
        # the Series bool-dtyped (shift().fillna(False) went through object
        # dtype and fired a pandas FutureWarning on every call).
        previous_squeeze_on = squeeze_on.shift(1, fill_value=False)

        # Firing occurs when previous bar was in squeeze, current bar is not
        squeeze_firing = previous_squeeze_on & squeeze_off

        logger.debug(
            f"Squeeze detection: on={squeeze_on.iloc[-1]}, "
            f"off={squeeze_off.iloc[-1]}, firing={squeeze_firing.iloc[-1]}"
        )

        return squeeze_on, squeeze_off, squeeze_firing

    def _classify_momentum_direction(
        self,
        momentum: pd.Series
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Classify momentum direction and calculate acceleration

        Args:
            momentum: Series of momentum histogram values

        Returns:
            Tuple of (direction_series, acceleration_series)

        Direction Classification:
        - BULLISH_INCREASING: momentum > 0 and momentum > prev_momentum
        - BULLISH_DECREASING: momentum > 0 and momentum <= prev_momentum
        - BEARISH_INCREASING: momentum < 0 and momentum < prev_momentum
        - BEARISH_DECREASING: momentum < 0 and momentum >= prev_momentum
        - FLAT: momentum is near zero or unchanged

        Acceleration is the rate of change of momentum (momentum of momentum).
        """
        # Calculate momentum change (acceleration)
        acceleration = momentum.diff()

        # Get previous momentum value
        prev_momentum = momentum.shift(1)

        # Classify each momentum value
        def classify_direction(row_data: Tuple[float, float, float]) -> str:
            """Classify single row momentum direction"""
            mom, prev_mom, accel = row_data

            # Handle NaN values
            if pd.isna(mom) or pd.isna(prev_mom):
                return MomentumDirection.FLAT.value

            # Define threshold for "flat" detection
            flat_threshold = 0.0001

            # Check for near-zero momentum (flat)
            if abs(mom) < flat_threshold:
                return MomentumDirection.FLAT.value

            # Positive momentum (bullish)
            if mom > 0:
                if mom > prev_mom:  # Increasing (accelerating upward)
                    return MomentumDirection.BULLISH_INCREASING.value
                else:  # Decreasing (decelerating)
                    return MomentumDirection.BULLISH_DECREASING.value

            # Negative momentum (bearish)
            else:
                if mom < prev_mom:  # Increasing negativity (accelerating downward)
                    return MomentumDirection.BEARISH_INCREASING.value
                else:  # Decreasing negativity (decelerating)
                    return MomentumDirection.BEARISH_DECREASING.value

        # Create DataFrame for vectorized classification
        direction_data = pd.DataFrame({
            'momentum': momentum,
            'prev_momentum': prev_momentum,
            'acceleration': acceleration
        })

        # Apply classification to each row
        direction_series = direction_data.apply(
            lambda row: classify_direction((row['momentum'], row['prev_momentum'], row['acceleration'])),
            axis=1
        )

        return direction_series, acceleration

    def _determine_histogram_color(
        self,
        momentum: float,
        prev_momentum: float
    ) -> str:
        """
        Determine histogram bar color based on momentum and direction

        Args:
            momentum: Current momentum value
            prev_momentum: Previous momentum value

        Returns:
            Color string: 'lime', 'green', 'red', or 'maroon'

        Color Logic (matching LazyBear Pine Script):
        - Lime: Positive momentum, increasing (bullish strength)
        - Green: Positive momentum, decreasing (bullish weakness)
        - Red: Negative momentum, increasing negativity (bearish strength)
        - Maroon: Negative momentum, decreasing negativity (bearish weakness)

        These colors provide visual feedback on momentum strength:
        - Bright colors (lime/red) = momentum accelerating
        - Dark colors (green/maroon) = momentum decelerating
        """
        # Handle NaN values
        if pd.isna(momentum) or pd.isna(prev_momentum):
            return 'gray'

        # Positive momentum (bullish)
        if momentum > 0:
            if momentum > prev_momentum:
                return 'lime'    # Bullish and strengthening
            else:
                return 'green'   # Bullish but weakening

        # Negative momentum (bearish)
        else:
            if momentum < prev_momentum:
                return 'red'     # Bearish and strengthening
            else:
                return 'maroon'  # Bearish but weakening

    def _calculate_squeeze_duration(self, squeeze_on_series: pd.Series) -> int:
        """
        Calculate how many consecutive bars have been in squeeze

        Args:
            squeeze_on_series: Boolean series of squeeze_on states

        Returns:
            Number of consecutive bars in squeeze (0 if not in squeeze)

        The squeeze duration is important for confidence scoring:
        - Longer squeezes tend to lead to stronger breakouts
        - Very short squeezes may be false signals
        """
        # Get the squeeze_on states as a list (reversed for counting from end)
        squeeze_states = squeeze_on_series.tolist()

        # If not currently in squeeze, duration is 0
        if not squeeze_states[-1]:
            return 0

        # Count consecutive True values from the end
        duration = 0
        for state in reversed(squeeze_states):
            if state:
                duration += 1
            else:
                break

        return duration

    def _calculate_confidence(
        self,
        squeeze_state: SqueezeState,
        squeeze_duration: int,
        momentum_strength: float,
        momentum_direction: MomentumDirection,
        signal: SignalType
    ) -> float:
        """
        Calculate confidence score for the signal

        Args:
            squeeze_state: Current squeeze state
            squeeze_duration: Number of bars in squeeze
            momentum_strength: Normalized momentum strength (0-1)
            momentum_direction: Classified momentum direction
            signal: Generated signal (BUY/SELL/HOLD)

        Returns:
            Confidence score between 0.0 and 1.0

        Confidence Factors:
        1. Squeeze state (firing = highest confidence)
        2. Squeeze duration (longer = higher confidence, up to a point)
        3. Momentum strength (stronger = higher confidence)
        4. Momentum direction (accelerating = higher confidence)

        Weight Distribution:
        - Squeeze state: 40%
        - Momentum strength: 30%
        - Momentum direction: 20%
        - Squeeze duration: 10%
        """
        # HOLD signals get low confidence by default
        if signal == SignalType.HOLD:
            return 0.25

        # Base confidence from squeeze state
        squeeze_state_confidence = {
            SqueezeState.SQUEEZE_FIRING: 1.0,    # Maximum - breakout moment
            SqueezeState.SQUEEZE_OFF: 0.8,       # High - breakout in progress
            SqueezeState.SQUEEZE_ON: 0.5,        # Medium - building pressure
            SqueezeState.NO_SQUEEZE: 0.3         # Low - no clear setup
        }
        state_conf = squeeze_state_confidence.get(squeeze_state, 0.3)

        # Confidence from momentum strength (0 to 1)
        momentum_conf = min(1.0, momentum_strength)

        # Confidence from momentum direction (accelerating = bonus)
        direction_conf = 0.5  # Default
        if momentum_direction in [MomentumDirection.BULLISH_INCREASING, MomentumDirection.BEARISH_INCREASING]:
            direction_conf = 1.0  # Accelerating momentum
        elif momentum_direction in [MomentumDirection.BULLISH_DECREASING, MomentumDirection.BEARISH_DECREASING]:
            direction_conf = 0.6  # Decelerating but still directional
        elif momentum_direction == MomentumDirection.FLAT:
            direction_conf = 0.2  # Flat momentum

        # Confidence from squeeze duration (optimal range: 5-20 bars)
        if squeeze_duration == 0:
            duration_conf = 0.3
        elif squeeze_duration < 5:
            duration_conf = 0.5  # Too short
        elif squeeze_duration <= 20:
            duration_conf = 1.0  # Optimal range
        else:
            duration_conf = 0.7  # Very long squeeze (may be range-bound)

        # Weighted average of confidence factors
        confidence = (
            state_conf * 0.40 +      # Squeeze state weight
            momentum_conf * 0.30 +   # Momentum strength weight
            direction_conf * 0.20 +  # Direction weight
            duration_conf * 0.10     # Duration weight
        )

        # Ensure confidence is within valid range
        confidence = max(0.1, min(1.0, confidence))

        logger.debug(
            f"Confidence calculation: state={state_conf:.2f}, "
            f"momentum={momentum_conf:.2f}, direction={direction_conf:.2f}, "
            f"duration={duration_conf:.2f}, total={confidence:.2f}"
        )

        return round(confidence, 2)  # non-price-round

    def _generate_signal(
        self,
        squeeze_state: SqueezeState,
        momentum_value: float,
        momentum_direction: MomentumDirection
    ) -> SignalType:
        """
        Generate trading signal based on squeeze state and momentum

        Args:
            squeeze_state: Current squeeze state
            momentum_value: Current momentum histogram value
            momentum_direction: Classified momentum direction

        Returns:
            SignalType (BUY, SELL, or HOLD)

        Signal Logic:
        - BUY: Squeeze fires + momentum positive + momentum increasing
        - SELL: Squeeze fires + momentum negative + momentum decreasing
        - HOLD: Still in squeeze OR momentum flat

        Additional Considerations:
        - Strong signals require squeeze firing or squeeze off
        - Momentum direction must confirm the signal
        - Flat momentum generates HOLD signals
        """
        # Handle NaN momentum
        if pd.isna(momentum_value):
            logger.debug("Signal: HOLD (NaN momentum)")
            return SignalType.HOLD

        # Flat momentum = HOLD regardless of squeeze state
        if momentum_direction == MomentumDirection.FLAT:
            logger.debug("Signal: HOLD (flat momentum)")
            return SignalType.HOLD

        # SQUEEZE FIRING - Highest priority signals
        if squeeze_state == SqueezeState.SQUEEZE_FIRING:
            if momentum_value > 0 and momentum_direction == MomentumDirection.BULLISH_INCREASING:
                # Perfect BUY setup: squeeze fires with accelerating bullish momentum
                logger.info("Signal: BUY (squeeze firing + bullish acceleration)")
                return SignalType.BUY
            elif momentum_value < 0 and momentum_direction == MomentumDirection.BEARISH_INCREASING:
                # Perfect SELL setup: squeeze fires with accelerating bearish momentum
                logger.info("Signal: SELL (squeeze firing + bearish acceleration)")
                return SignalType.SELL
            elif momentum_value > 0:
                # Squeeze fires with positive momentum (even if decelerating)
                logger.info("Signal: BUY (squeeze firing + positive momentum)")
                return SignalType.BUY
            elif momentum_value < 0:
                # Squeeze fires with negative momentum (even if decelerating)
                logger.info("Signal: SELL (squeeze firing + negative momentum)")
                return SignalType.SELL

        # SQUEEZE OFF - Breakout in progress
        if squeeze_state == SqueezeState.SQUEEZE_OFF:
            if momentum_value > 0 and momentum_direction == MomentumDirection.BULLISH_INCREASING:
                logger.debug("Signal: BUY (squeeze off + bullish acceleration)")
                return SignalType.BUY
            elif momentum_value < 0 and momentum_direction == MomentumDirection.BEARISH_INCREASING:
                logger.debug("Signal: SELL (squeeze off + bearish acceleration)")
                return SignalType.SELL
            # Decelerating momentum during squeeze_off = potential reversal, hold
            else:
                logger.debug("Signal: HOLD (squeeze off but decelerating)")
                return SignalType.HOLD

        # SQUEEZE ON - Building pressure, wait for breakout
        if squeeze_state == SqueezeState.SQUEEZE_ON:
            # Strong acceleration during squeeze can be early entry
            if momentum_direction == MomentumDirection.BULLISH_INCREASING and momentum_value > 0:
                logger.debug("Signal: BUY (in squeeze + strong bullish buildup)")
                return SignalType.BUY
            elif momentum_direction == MomentumDirection.BEARISH_INCREASING and momentum_value < 0:
                logger.debug("Signal: SELL (in squeeze + strong bearish buildup)")
                return SignalType.SELL
            else:
                logger.debug("Signal: HOLD (in squeeze, waiting for breakout)")
                return SignalType.HOLD

        # NO_SQUEEZE - Default to HOLD
        logger.debug("Signal: HOLD (no clear squeeze state)")
        return SignalType.HOLD

    def calculate(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Calculate Enhanced Squeeze Momentum on OHLCV data

        Args:
            df: DataFrame with columns: open, high, low, close, volume

        Returns:
            DataFrame with added columns:
            - bb_upper, bb_basis, bb_lower: Bollinger Bands
            - kc_upper, kc_basis, kc_lower: Keltner Channels
            - squeeze_on: Boolean - squeeze is active
            - squeeze_off: Boolean - squeeze is released
            - squeeze_firing: Boolean - squeeze just fired
            - sqz_momentum: Momentum histogram value
            - sqz_acceleration: Rate of momentum change
            - sqz_direction: Momentum direction classification
            - sqz_color: Histogram bar color
            - sqz_signal: Trading signal (BUY/SELL/HOLD)
            - sqz_confidence: Signal confidence (0-1)

            Returns None if insufficient data or calculation fails.
        """
        # Validate input DataFrame has required columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            return None

        # Check minimum data requirements
        min_periods = max(self.bb_length, self.kc_length, self.momentum_length) + 5
        if len(df) < min_periods:
            logger.warning(
                f"Insufficient data for Enhanced SQZMOM: need {min_periods}, got {len(df)}"
            )
            return None

        # Reject a non-unique index (DEFER-21-01, 2026-08-27).
        #
        # MECHANISM: every label lookup in this module -- `prev_momentum.loc[row.name]`
        # in the `sqz_color` apply, `result_df.loc[:row.name, 'squeeze_on']` in the
        # confidence closure -- returns a SERIES instead of a scalar when the index
        # carries a duplicate label. `_determine_histogram_color` then evaluates
        # `pd.isna(<Series>)` in a boolean context and raises "The truth value of a
        # Series is ambiguous", which the broad `except Exception` at the end of this
        # method converts into `return None`.
        #
        # WHY THIS RAISES INSTEAD OF RETURNING None: a `None` from a VOTING indicator
        # is invisible downstream. handlers/analysis.py:146 guards
        # `if sqz_df is not None and not sqz_df.empty`, so the SQZMOM leg simply
        # vanished from the aggregate vote -- the endpoint returned a well-formed 200
        # computed from one fewer voter, with `"sqzmom": null` as the only trace. Loud
        # failure is the ratified direction: the caller now gets a named error that
        # identifies the offending candles instead of a silently degraded signal.
        #
        # PLACEMENT IS LOAD-BEARING: this sits BEFORE the `try:` below. Moved inside
        # it, this module's own `except Exception` would swallow the ValueError
        # straight back into the `None` the check exists to remove.
        #
        # The two checks above keep returning None deliberately. This ADDS a
        # rejection; it does not convert the existing validation paths into raises.
        if not df.index.is_unique:
            duplicated = df.index[df.index.duplicated()].unique()
            detail = (
                f"Enhanced SQZMOM received a non-unique index: {len(duplicated)} "
                f"duplicated label(s) {[str(label) for label in duplicated]}. "
                f"Label lookups on a non-unique index return a Series instead of a "
                f"scalar, so this frame cannot be scored. Rejecting it rather than "
                f"returning None, which would silently drop the SQZMOM leg from the "
                f"aggregate vote (DEFER-21-01)."
            )
            logger.error(detail)
            raise ValueError(detail)

        try:
            # Create a copy to avoid modifying the original DataFrame
            result_df = df.copy()

            # Step 1: Calculate Bollinger Bands
            bb_upper, bb_basis, bb_lower = self._calculate_bollinger_bands(df['close'])
            result_df['bb_upper'] = bb_upper
            result_df['bb_basis'] = bb_basis
            result_df['bb_lower'] = bb_lower

            # Step 2: Calculate Keltner Channels
            kc_upper, kc_basis, kc_lower = self._calculate_keltner_channels(df)
            result_df['kc_upper'] = kc_upper
            result_df['kc_basis'] = kc_basis
            result_df['kc_lower'] = kc_lower

            # Step 3: Detect squeeze states
            squeeze_on, squeeze_off, squeeze_firing = self._detect_squeeze_state(
                bb_upper, bb_lower, kc_upper, kc_lower
            )
            result_df['squeeze_on'] = squeeze_on
            result_df['squeeze_off'] = squeeze_off
            result_df['squeeze_firing'] = squeeze_firing

            # Step 4: Calculate momentum histogram
            momentum = self._calculate_momentum_histogram(df)
            result_df['sqz_momentum'] = momentum

            # Step 5: Classify momentum direction and calculate acceleration
            direction_series, acceleration = self._classify_momentum_direction(momentum)
            result_df['sqz_direction'] = direction_series
            result_df['sqz_acceleration'] = acceleration

            # Step 6: Determine histogram colors
            prev_momentum = momentum.shift(1)
            result_df['sqz_color'] = result_df.apply(
                lambda row: self._determine_histogram_color(
                    row['sqz_momentum'],
                    prev_momentum.loc[row.name] if row.name in prev_momentum.index else np.nan
                ),
                axis=1
            )

            # Step 7: Generate trading signals
            def generate_row_signal(row: pd.Series) -> str:
                """Generate signal for a single row"""
                # Determine squeeze state
                if row['squeeze_firing']:
                    state = SqueezeState.SQUEEZE_FIRING
                elif row['squeeze_off']:
                    state = SqueezeState.SQUEEZE_OFF
                elif row['squeeze_on']:
                    state = SqueezeState.SQUEEZE_ON
                else:
                    state = SqueezeState.NO_SQUEEZE

                # Get momentum direction
                try:
                    direction = MomentumDirection(row['sqz_direction'])
                except ValueError:
                    direction = MomentumDirection.FLAT

                # Generate signal
                signal = self._generate_signal(state, row['sqz_momentum'], direction)
                return signal.value

            result_df['sqz_signal'] = result_df.apply(generate_row_signal, axis=1)

            # Step 8: Calculate confidence scores
            #
            # LOOK-AHEAD FIX (TA-AGG-04, 2026-08-27). The momentum-strength
            # normaliser below read `result_df['sqz_momentum'].abs().max()` --
            # the maximum over the WHOLE frame, including bars AFTER the row
            # being scored. `sqz_confidence` at bar t therefore rose
            # retroactively whenever a larger |momentum| arrived later, which
            # is look-ahead leakage in the series path. Measured on a 400-bar
            # synthetic walk: 39 of 250 probed bars disagreed with their own
            # prefix computation; worst case 0.80 vs 0.85 -- percentage
            # points, not float noise.
            #
            # An expanding max is causal: at row i it sees bars 0..i only. At
            # `.iloc[-1]` the two agree exactly, so every production consumer
            # (get_signal, IndicatorService.calculate_sqzmom_enhanced, the
            # /aggregate handler, backtesting/replay/build_indicator_frames)
            # is byte-for-byte unaffected -- all of them read the last row.
            # Only whole-series / backtest reads change, from inflated to
            # honest.
            #
            # Early bars now get a smaller denominator and so a noisier
            # strength. That is the correct trade: causal-but-noisy beats
            # smooth-but-leaky. Pinned by tests/test_leakage_regression.py::
            # test_sqzmom_enhanced_row_at_t_is_independent_of_future_bars.
            # Held as a numpy array and indexed POSITIONALLY. A label
            # lookup returns a Series rather than a scalar when the frame
            # carries duplicate index labels, and this repo's kline
            # history has had holes and repairs; positional indexing has
            # no index-shape dependency at all.
            expanding_max_momentum = (
                result_df['sqz_momentum'].abs().expanding().max().to_numpy()
            )

            def calculate_row_confidence(row: pd.Series, position: int) -> float:
                """Calculate confidence for a single row"""
                # Determine squeeze state
                if row['squeeze_firing']:
                    state = SqueezeState.SQUEEZE_FIRING
                elif row['squeeze_off']:
                    state = SqueezeState.SQUEEZE_OFF
                elif row['squeeze_on']:
                    state = SqueezeState.SQUEEZE_ON
                else:
                    state = SqueezeState.NO_SQUEEZE

                # Calculate squeeze duration up to this row
                duration = self._calculate_squeeze_duration(
                    result_df.loc[:row.name, 'squeeze_on']
                )

                # Calculate momentum strength (normalized) against the
                # CAUSAL running maximum -- see the LOOK-AHEAD FIX note above.
                max_momentum = expanding_max_momentum[position]
                momentum_strength = abs(row['sqz_momentum']) / max_momentum if max_momentum > 0 else 0

                # Get momentum direction
                try:
                    direction = MomentumDirection(row['sqz_direction'])
                except ValueError:
                    direction = MomentumDirection.FLAT

                # Get signal
                try:
                    signal = SignalType(row['sqz_signal'])
                except ValueError:
                    signal = SignalType.HOLD

                return self._calculate_confidence(
                    state, duration, momentum_strength, direction, signal
                )

            # Explicit positional walk rather than .apply(axis=1): the
            # row's position is needed for the causal maximum above, and
            # deriving it from the index would reintroduce the duplicate
            # label hazard the array lookup exists to avoid.
            result_df['sqz_confidence'] = [
                calculate_row_confidence(result_df.iloc[position], position)
                for position in range(len(result_df))
            ]

            # Log successful calculation
            logger.info(
                f"Enhanced SQZMOM calculated successfully. Last values: "
                f"squeeze_on={result_df['squeeze_on'].iloc[-1]}, "
                f"squeeze_firing={result_df['squeeze_firing'].iloc[-1]}, "
                f"momentum={result_df['sqz_momentum'].iloc[-1]:.6f}, "
                f"signal={result_df['sqz_signal'].iloc[-1]}, "
                f"confidence={result_df['sqz_confidence'].iloc[-1]:.2f}"
            )

            return result_df

        except Exception as e:
            logger.error(f"Error calculating Enhanced Squeeze Momentum: {e}", exc_info=True)
            return None

    def get_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get current trading signal with comprehensive metadata

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dictionary containing:
            - signal: SignalType value ('BUY', 'SELL', 'HOLD')
            - confidence: float (0-1)
            - metadata: SqueezeMetadata as dictionary

        This is the primary method to call for getting trading signals.
        It calculates all indicators and returns a complete analysis.
        """
        # Calculate all indicators
        result_df = self.calculate(df)

        # Handle calculation failure
        if result_df is None:
            return {
                'signal': SignalType.HOLD.value,
                'confidence': 0.0,
                'error': 'Failed to calculate Enhanced SQZMOM',
                'metadata': None
            }

        # Get the most recent (last) row
        latest = result_df.iloc[-1]

        # Determine current squeeze state
        if latest['squeeze_firing']:
            squeeze_state = SqueezeState.SQUEEZE_FIRING
        elif latest['squeeze_off']:
            squeeze_state = SqueezeState.SQUEEZE_OFF
        elif latest['squeeze_on']:
            squeeze_state = SqueezeState.SQUEEZE_ON
        else:
            squeeze_state = SqueezeState.NO_SQUEEZE

        # Calculate squeeze duration
        squeeze_duration = self._calculate_squeeze_duration(result_df['squeeze_on'])

        # Get momentum direction
        try:
            momentum_direction = MomentumDirection(latest['sqz_direction'])
        except ValueError:
            momentum_direction = MomentumDirection.FLAT

        # Calculate momentum strength (normalized 0-1)
        max_momentum = result_df['sqz_momentum'].abs().max()
        momentum_strength = abs(latest['sqz_momentum']) / max_momentum if max_momentum > 0 else 0.0

        # Calculate band width ratio (BB width / KC width)
        bb_width = latest['bb_upper'] - latest['bb_lower']
        kc_width = latest['kc_upper'] - latest['kc_lower']
        band_width_ratio = bb_width / kc_width if kc_width > 0 else 1.0

        # Get histogram values (last 10)
        histogram_values = result_df['sqz_momentum'].dropna().tolist()

        # Build comprehensive metadata
        metadata = SqueezeMetadata(
            squeeze_state=squeeze_state,
            squeeze_on=bool(latest['squeeze_on']),
            squeeze_off=bool(latest['squeeze_off']),
            squeeze_firing=bool(latest['squeeze_firing']),
            squeeze_duration=squeeze_duration,
            momentum_value=float(latest['sqz_momentum']) if not pd.isna(latest['sqz_momentum']) else 0.0,
            momentum_direction=momentum_direction,
            momentum_acceleration=float(latest['sqz_acceleration']) if not pd.isna(latest['sqz_acceleration']) else 0.0,
            momentum_strength=float(momentum_strength),
            histogram=histogram_values,
            histogram_color=str(latest['sqz_color']),
            bb_upper=float(latest['bb_upper']),
            bb_basis=float(latest['bb_basis']),
            bb_lower=float(latest['bb_lower']),
            kc_upper=float(latest['kc_upper']),
            kc_basis=float(latest['kc_basis']),
            kc_lower=float(latest['kc_lower']),
            current_price=float(df['close'].iloc[-1]),
            band_width_ratio=float(band_width_ratio)
        )

        # Get signal and confidence
        signal = SignalType(latest['sqz_signal'])
        confidence = float(latest['sqz_confidence'])

        # Build and return the result
        return {
            'signal': signal.value,
            'confidence': confidence,
            'metadata': metadata.to_dict()
        }

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform detailed analysis with additional insights

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dictionary with signal, confidence, metadata, and analysis insights

        This method provides additional analysis beyond get_signal(), including:
        - Trend analysis
        - Signal strength assessment
        - Risk/reward considerations
        """
        # Get base signal and metadata
        result = self.get_signal(df)

        # If calculation failed, return early
        if result.get('error'):
            return result

        # Extract metadata for analysis
        metadata = result['metadata']

        # Generate analysis insights
        insights = []

        # Squeeze state analysis
        if metadata['squeeze_firing']:
            insights.append("ALERT: Squeeze just fired - high probability breakout moment")
        elif metadata['squeeze_on']:
            insights.append(f"In squeeze for {metadata['squeeze_duration']} bars - pressure building")
        elif metadata['squeeze_off']:
            insights.append("Squeeze released - breakout in progress")

        # Momentum analysis
        if metadata['momentum_direction'] == MomentumDirection.BULLISH_INCREASING.value:
            insights.append("Strong bullish momentum - accelerating upward")
        elif metadata['momentum_direction'] == MomentumDirection.BEARISH_INCREASING.value:
            insights.append("Strong bearish momentum - accelerating downward")
        elif metadata['momentum_direction'] == MomentumDirection.BULLISH_DECREASING.value:
            insights.append("Bullish momentum fading - watch for reversal")
        elif metadata['momentum_direction'] == MomentumDirection.BEARISH_DECREASING.value:
            insights.append("Bearish momentum fading - watch for reversal")

        # Band width analysis
        if metadata['band_width_ratio'] < 0.8:
            insights.append("Very tight squeeze - expect significant move")
        elif metadata['band_width_ratio'] < 1.0:
            insights.append("Moderate squeeze - building pressure")
        else:
            insights.append("No squeeze - normal volatility")

        # Signal strength assessment
        confidence = result['confidence']
        if confidence >= 0.8:
            strength = "STRONG"
        elif confidence >= 0.6:
            strength = "MODERATE"
        elif confidence >= 0.4:
            strength = "WEAK"
        else:
            strength = "VERY WEAK"

        # Add analysis to result
        result['analysis'] = {
            'signal_strength': strength,
            'insights': insights,
            'recommendation': self._generate_recommendation(
                result['signal'],
                confidence,
                metadata
            )
        }

        return result

    def _generate_recommendation(
        self,
        signal: str,
        confidence: float,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Generate human-readable trading recommendation

        Args:
            signal: Signal type (BUY/SELL/HOLD)
            confidence: Confidence score
            metadata: Analysis metadata

        Returns:
            String with trading recommendation
        """
        if signal == 'HOLD':
            if metadata['squeeze_on']:
                return (
                    f"WAIT - Currently in squeeze (duration: {metadata['squeeze_duration']} bars). "
                    "Monitor for squeeze firing signal before entry."
                )
            else:
                return "HOLD - No clear setup. Wait for better entry conditions."

        action = "LONG" if signal == 'BUY' else "SHORT"
        strength = "Strong" if confidence >= 0.7 else "Moderate" if confidence >= 0.5 else "Weak"

        if metadata['squeeze_firing']:
            return (
                f"{strength} {action} ENTRY - Squeeze fired with "
                f"{metadata['momentum_direction'].replace('_', ' ').lower()}. "
                f"High probability breakout setup."
            )
        elif metadata['squeeze_off']:
            return (
                f"{strength} {action} - Breakout in progress with "
                f"{metadata['momentum_direction'].replace('_', ' ').lower()}. "
                f"Consider entry on pullback."
            )
        else:
            return (
                f"{strength} {action} signal with {confidence:.0%} confidence. "
                f"Current momentum: {metadata['momentum_direction'].replace('_', ' ').lower()}."
            )


# Module-level function for quick signal calculation
def calculate_squeeze_momentum(
    df: pd.DataFrame,
    bb_length: int = 20,
    bb_mult: float = 2.0,
    kc_length: int = 20,
    kc_mult: float = 1.5,
    momentum_length: int = 12
) -> Dict[str, Any]:
    """
    Convenience function to calculate Enhanced Squeeze Momentum

    Args:
        df: DataFrame with OHLCV data
        bb_length: Bollinger Bands period
        bb_mult: Bollinger Bands multiplier
        kc_length: Keltner Channel period
        kc_mult: Keltner Channel multiplier
        momentum_length: Linear regression period

    Returns:
        Dictionary with signal, confidence, and metadata

    Example:
        >>> result = calculate_squeeze_momentum(ohlcv_df)
        >>> print(f"Signal: {result['signal']}, Confidence: {result['confidence']}")
    """
    indicator = EnhancedSqueezeMomentum(
        bb_length=bb_length,
        bb_mult=bb_mult,
        kc_length=kc_length,
        kc_mult=kc_mult,
        momentum_length=momentum_length
    )
    return indicator.get_signal(df)
