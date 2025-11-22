"""
Squeeze Momentum Indicator (SQZMOM) by LazyBear
Purpose: Identify low-volatility squeeze conditions and momentum direction for breakout trading

The Squeeze Momentum Indicator combines Bollinger Bands and Keltner Channels to:
1. Detect "squeeze" conditions (low volatility compression)
2. Measure momentum using linear regression
3. Signal potential breakout directions

Original Pine Script by LazyBear - Python implementation for crypto trading
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple, Dict
from scipy import stats
from app.models import SignalType

logger = logging.getLogger(__name__)


class SqueezeMomentumIndicator:
    """
    Squeeze Momentum Indicator Implementation

    Identifies low-volatility squeeze conditions (Bollinger Bands inside Keltner Channels)
    and calculates momentum direction using linear regression for potential breakout trading.

    Components:
    1. Bollinger Bands (BB): Volatility-based bands using standard deviation
    2. Keltner Channels (KC): ATR-based channels using true range
    3. Squeeze Detection: BB inside KC = squeeze ON, BB outside KC = squeeze OFF
    4. Momentum: Linear regression of price deviation from midpoint

    Trading Logic:
    - Squeeze ON + Positive momentum acceleration = Potential LONG breakout
    - Squeeze ON + Negative momentum acceleration = Potential SHORT breakout
    - Squeeze OFF = Breakout in progress, follow momentum direction
    """

    def __init__(
        self,
        bb_length: int = 20,
        bb_mult: float = 2.0,
        kc_length: int = 20,
        kc_mult: float = 1.5,
        use_true_range: bool = True
    ):
        """
        Initialize Squeeze Momentum Indicator

        Args:
            bb_length: Bollinger Bands period (default: 20)
            bb_mult: Bollinger Bands standard deviation multiplier (default: 2.0)
            kc_length: Keltner Channel period (default: 20)
            kc_mult: Keltner Channel ATR multiplier (default: 1.5)
            use_true_range: Use True Range for KC calculation vs simple high-low (default: True)

        Standard Parameters:
        - BB: 20-period SMA ± 2 std devs
        - KC: 20-period SMA ± 1.5 × ATR
        - True Range: max(high-low, abs(high-prev_close), abs(low-prev_close))
        """
        self.bb_length = bb_length
        self.bb_mult = bb_mult
        self.kc_length = kc_length
        self.kc_mult = kc_mult
        self.use_true_range = use_true_range

        logger.info(
            f"Squeeze Momentum Indicator initialized: "
            f"BB({bb_length}, {bb_mult}), KC({kc_length}, {kc_mult}), "
            f"TrueRange={use_true_range}"
        )

    def _calculate_bollinger_bands(
        self,
        close: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands

        Args:
            close: Close price series

        Returns:
            Tuple of (upper_band, basis, lower_band) as pandas Series

        Formula:
            basis = SMA(close, bb_length)
            dev = bb_mult × StdDev(close, bb_length)
            upper_band = basis + dev
            lower_band = basis - dev
        """
        # Calculate simple moving average (basis/middle line)
        basis = close.rolling(window=self.bb_length).mean()

        # Calculate standard deviation
        std_dev = close.rolling(window=self.bb_length).std()

        # Calculate deviation (multiplied by bb_mult)
        dev = self.bb_mult * std_dev

        # Calculate upper and lower bands
        upper_band = basis + dev
        lower_band = basis - dev

        logger.debug(
            f"BB calculated: basis={basis.iloc[-1]:.2f}, "
            f"upper={upper_band.iloc[-1]:.2f}, lower={lower_band.iloc[-1]:.2f}"
        )

        return upper_band, basis, lower_band

    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate True Range (TR)

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            Series of True Range values

        Formula:
            TR = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )

        True Range captures volatility including gaps between periods.
        """
        # Current period's high - low
        high_low = df['high'] - df['low']

        # abs(current high - previous close)
        high_prev_close = (df['high'] - df['close'].shift(1)).abs()

        # abs(current low - previous close)
        low_prev_close = (df['low'] - df['close'].shift(1)).abs()

        # True Range is the maximum of these three values
        true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

        logger.debug(f"True Range calculated: current={true_range.iloc[-1]:.4f}")

        return true_range

    def _calculate_keltner_channels(
        self,
        df: pd.DataFrame
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Keltner Channels

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            Tuple of (upper_kc, ma, lower_kc) as pandas Series

        Formula:
            ma = SMA(close, kc_length)
            range = True Range if use_true_range else (high - low)
            rangema = SMA(range, kc_length)
            upper_kc = ma + rangema × kc_mult
            lower_kc = ma - rangema × kc_mult
        """
        # Calculate moving average (middle line)
        ma = df['close'].rolling(window=self.kc_length).mean()

        # Calculate range (True Range or simple high-low)
        if self.use_true_range:
            range_values = self._calculate_true_range(df)
        else:
            # Simple range: high - low
            range_values = df['high'] - df['low']

        # Calculate average range
        rangema = range_values.rolling(window=self.kc_length).mean()

        # Calculate upper and lower Keltner Channels
        upper_kc = ma + (rangema * self.kc_mult)
        lower_kc = ma - (rangema * self.kc_mult)

        logger.debug(
            f"KC calculated: ma={ma.iloc[-1]:.2f}, "
            f"upper={upper_kc.iloc[-1]:.2f}, lower={lower_kc.iloc[-1]:.2f}"
        )

        return upper_kc, ma, lower_kc

    def _calculate_momentum(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate momentum using linear regression

        Args:
            df: DataFrame with 'high', 'low', 'close' columns

        Returns:
            Series of momentum values

        Formula (from Pine Script):
            val = linreg(source - avg(avg(highest(high, lengthKC), lowest(low, lengthKC)),
                         sma(close, lengthKC)), lengthKC, 0)

        Breakdown:
        1. highest_high = highest(high, kc_length)
        2. lowest_low = lowest(low, kc_length)
        3. hl_avg = avg(highest_high, lowest_low)
        4. close_sma = sma(close, kc_length)
        5. midpoint = avg(hl_avg, close_sma)
        6. deviation = source - midpoint
        7. momentum = linreg(deviation, kc_length, 0)

        This measures how price deviates from the midpoint with linear regression smoothing.
        """
        # Calculate highest high over kc_length periods
        highest_high = df['high'].rolling(window=self.kc_length).max()

        # Calculate lowest low over kc_length periods
        lowest_low = df['low'].rolling(window=self.kc_length).min()

        # Average of highest high and lowest low
        hl_avg = (highest_high + lowest_low) / 2

        # Simple moving average of close
        close_sma = df['close'].rolling(window=self.kc_length).mean()

        # Midpoint: average of hl_avg and close_sma
        midpoint = (hl_avg + close_sma) / 2

        # Deviation: source (close) minus midpoint
        deviation = df['close'] - midpoint

        # Calculate linear regression of deviation
        # Linear regression returns the fitted value at offset 0 (current point)
        momentum = self._rolling_linreg(deviation, self.kc_length)

        logger.debug(f"Momentum calculated: current={momentum.iloc[-1]:.4f}")

        return momentum

    def _rolling_linreg(self, series: pd.Series, period: int) -> pd.Series:
        """
        Calculate rolling linear regression values

        Args:
            series: Input data series
            period: Regression window period

        Returns:
            Series of linear regression fitted values at offset 0

        For each window, fits a linear regression y = mx + b and returns
        the fitted value at x=0 (the current point).

        This is equivalent to Pine Script's linreg(source, length, offset=0)
        """
        def linreg_value(y_values):
            """Calculate linear regression fitted value at x=0"""
            if len(y_values) < period:
                return np.nan

            # Create x values (0, 1, 2, ..., period-1)
            x = np.arange(len(y_values))

            # Remove NaN values
            mask = ~np.isnan(y_values)
            if mask.sum() < 2:  # Need at least 2 points for regression
                return np.nan

            x_clean = x[mask]
            y_clean = y_values[mask]

            try:
                # Perform linear regression
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_clean, y_clean)

                # Return fitted value at x=0 (most recent point in window)
                # Note: In the rolling window, index 0 is the oldest point
                # We want the value at the newest point, which is at x = period - 1
                fitted_value = slope * (len(y_values) - 1) + intercept

                return fitted_value

            except Exception as e:
                logger.warning(f"Linear regression failed: {e}")
                return np.nan

        # Apply rolling linear regression
        result = series.rolling(window=period).apply(linreg_value, raw=True)

        return result

    def calculate(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Calculate Squeeze Momentum Indicator on OHLCV data

        Args:
            df: DataFrame with columns: open, high, low, close, volume

        Returns:
            DataFrame with added columns:
            - bb_upper, bb_basis, bb_lower: Bollinger Bands
            - kc_upper, kc_basis, kc_lower: Keltner Channels
            - squeeze_on: Bool - Squeeze is active (BB inside KC)
            - squeeze_off: Bool - Squeeze just released (BB outside KC)
            - no_squeeze: Bool - Neither squeeze nor release
            - sqz_momentum: Momentum value (positive = bullish, negative = bearish)
            - sqz_color: Signal color ('lime', 'green', 'red', 'maroon')
            - sqz_signal: Trading signal (BUY/SELL/HOLD)
            - sqz_confidence: Signal confidence (0-1)

        Returns None if insufficient data.
        """
        # Validate input data
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing required columns. Need: {required_cols}")
            return None

        # Check minimum data requirements
        min_periods = max(self.bb_length, self.kc_length) + 1
        if len(df) < min_periods:
            logger.warning(
                f"Insufficient data for SQZMOM: need {min_periods}, got {len(df)}"
            )
            return None

        try:
            # Make a copy to avoid modifying original
            result_df = df.copy()

            # 1. Calculate Bollinger Bands
            bb_upper, bb_basis, bb_lower = self._calculate_bollinger_bands(df['close'])
            result_df['bb_upper'] = bb_upper
            result_df['bb_basis'] = bb_basis
            result_df['bb_lower'] = bb_lower

            # 2. Calculate Keltner Channels
            kc_upper, kc_basis, kc_lower = self._calculate_keltner_channels(df)
            result_df['kc_upper'] = kc_upper
            result_df['kc_basis'] = kc_basis
            result_df['kc_lower'] = kc_lower

            # 3. Detect squeeze conditions
            # Squeeze ON: BB is inside KC (lower BB > lower KC AND upper BB < upper KC)
            result_df['squeeze_on'] = (bb_lower > kc_lower) & (bb_upper < kc_upper)

            # Squeeze OFF: BB is outside KC (lower BB < lower KC AND upper BB > upper KC)
            result_df['squeeze_off'] = (bb_lower < kc_lower) & (bb_upper > kc_upper)

            # No Squeeze: Neither condition (transitional state)
            result_df['no_squeeze'] = ~result_df['squeeze_on'] & ~result_df['squeeze_off']

            # 4. Calculate momentum
            result_df['sqz_momentum'] = self._calculate_momentum(df)

            # 5. Generate color signals (matching Pine Script logic)
            # Determine if momentum is increasing or decreasing
            momentum_prev = result_df['sqz_momentum'].shift(1)
            momentum_increasing = result_df['sqz_momentum'] > momentum_prev

            # Color logic from Pine Script:
            # bcolor = iff(val > 0,
            #              iff(val > nz(val[1]), lime, green),
            #              iff(val < nz(val[1]), red, maroon))

            conditions = [
                (result_df['sqz_momentum'] > 0) & momentum_increasing,  # lime
                (result_df['sqz_momentum'] > 0) & ~momentum_increasing,  # green
                (result_df['sqz_momentum'] < 0) & ~momentum_increasing,  # red (decreasing, more negative)
                (result_df['sqz_momentum'] < 0) & momentum_increasing,   # maroon (increasing, less negative)
            ]
            colors = ['lime', 'green', 'red', 'maroon']
            result_df['sqz_color'] = np.select(conditions, colors, default='gray')

            # 6. Generate trading signals
            result_df['sqz_signal'] = result_df.apply(
                lambda row: self._generate_signal_for_row(row),
                axis=1
            )

            # 7. Calculate confidence
            result_df['sqz_confidence'] = result_df.apply(
                lambda row: self._calculate_confidence(row),
                axis=1
            )

            logger.info(
                f"SQZMOM calculated successfully. Last values: "
                f"squeeze_on={result_df['squeeze_on'].iloc[-1]}, "
                f"momentum={result_df['sqz_momentum'].iloc[-1]:.4f}, "
                f"signal={result_df['sqz_signal'].iloc[-1]}"
            )

            return result_df

        except Exception as e:
            logger.error(f"Error calculating Squeeze Momentum: {e}", exc_info=True)
            return None

    def _generate_signal_for_row(self, row: pd.Series) -> str:
        """
        Generate trading signal for a single row

        Args:
            row: DataFrame row with SQZMOM data

        Returns:
            Signal string: 'BUY', 'SELL', or 'HOLD'

        Signal Logic:
        - BUY: Squeeze released + positive momentum (lime/green bars)
        - SELL: Squeeze released + negative momentum (red/maroon bars)
        - HOLD: Squeeze active or unclear momentum
        """
        # Check for NaN values
        if pd.isna(row['sqz_momentum']):
            return 'HOLD'

        momentum = row['sqz_momentum']
        color = row['sqz_color']
        squeeze_on = row['squeeze_on']
        squeeze_off = row['squeeze_off']

        # Strong signals: Squeeze release with clear momentum direction
        if squeeze_off:
            if color in ['lime', 'green']:  # Positive momentum
                return 'BUY'
            elif color in ['red', 'maroon']:  # Negative momentum
                return 'SELL'

        # Moderate signals: Squeeze active but momentum accelerating
        if squeeze_on:
            if color == 'lime':  # Momentum accelerating up (potential long breakout)
                return 'BUY'
            elif color == 'red':  # Momentum accelerating down (potential short breakout)
                return 'SELL'

        # Default: Hold for unclear conditions
        return 'HOLD'

    def _calculate_confidence(self, row: pd.Series) -> float:
        """
        Calculate confidence score for the signal

        Args:
            row: DataFrame row with SQZMOM data

        Returns:
            Confidence score (0.0 to 1.0)

        Confidence Factors:
        1. Momentum magnitude (stronger momentum = higher confidence)
        2. Squeeze state (squeeze release = higher confidence)
        3. Color (accelerating momentum = higher confidence)
        """
        # Check for NaN values
        if pd.isna(row['sqz_momentum']):
            return 0.0

        momentum = abs(row['sqz_momentum'])
        color = row['sqz_color']
        squeeze_on = row['squeeze_on']
        squeeze_off = row['squeeze_off']

        # Base confidence from momentum magnitude
        # Normalize to 0-1 range (assuming typical momentum range is 0-10)
        base_confidence = min(momentum / 10.0, 1.0)

        # Boost for squeeze release (breakout confirmation)
        if squeeze_off:
            base_confidence *= 1.3

        # Boost for accelerating momentum (lime or red bars)
        if color in ['lime', 'red']:
            base_confidence *= 1.2

        # Reduce for squeeze active (still building pressure)
        if squeeze_on:
            base_confidence *= 0.8

        # Ensure confidence is in valid range
        confidence = max(0.1, min(1.0, base_confidence))

        return round(confidence, 2)

    def get_signal(self, df: pd.DataFrame) -> Dict:
        """
        Get current trading signal with detailed information

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dictionary with:
            - signal: 'BUY'|'SELL'|'HOLD'
            - squeeze_on: bool (squeeze active)
            - squeeze_off: bool (squeeze released)
            - momentum: float (momentum value)
            - color: str (signal color)
            - strength: float (0-1, momentum strength)
            - confidence: float (0-1, signal confidence)
            - bb_bands: dict (Bollinger Bands values)
            - kc_channels: dict (Keltner Channels values)

        Returns error dict if calculation fails.
        """
        result_df = self.calculate(df)

        if result_df is None:
            return {
                'error': 'Failed to calculate SQZMOM',
                'signal': 'HOLD',
                'confidence': 0.0
            }

        # Get the most recent row
        latest = result_df.iloc[-1]

        # Calculate momentum strength (normalized)
        momentum = latest['sqz_momentum']
        max_momentum = result_df['sqz_momentum'].abs().max()
        strength = abs(momentum) / max_momentum if max_momentum > 0 else 0.0

        return {
            'signal': latest['sqz_signal'],
            'squeeze_on': bool(latest['squeeze_on']),
            'squeeze_off': bool(latest['squeeze_off']),
            'no_squeeze': bool(latest['no_squeeze']),
            'momentum': round(float(momentum), 4),
            'color': latest['sqz_color'],
            'strength': round(float(strength), 2),
            'confidence': float(latest['sqz_confidence']),
            'bb_bands': {
                'upper': round(float(latest['bb_upper']), 2),
                'basis': round(float(latest['bb_basis']), 2),
                'lower': round(float(latest['bb_lower']), 2)
            },
            'kc_channels': {
                'upper': round(float(latest['kc_upper']), 2),
                'basis': round(float(latest['kc_basis']), 2),
                'lower': round(float(latest['kc_lower']), 2)
            }
        }
