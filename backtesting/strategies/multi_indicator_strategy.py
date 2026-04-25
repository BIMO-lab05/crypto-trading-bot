#!/usr/bin/env python3
"""
Multi-Indicator Trading Strategy
Phase 2.1 - Strategy Enhancement

Combines multiple technical indicators for robust signal generation:
- RSI: Momentum/overbought-oversold detection
- MACD: Trend confirmation and divergence
- Bollinger Bands: Volatility-based entry/exit
- Volume: Confirmation of price moves

Strategy Logic:
- LONG when: RSI oversold + MACD bullish cross + Price near lower BB + Volume surge
- SHORT when: RSI overbought + MACD bearish cross + Price near upper BB + Volume surge
- EXIT when: Opposite signals or profit target/stop loss hit

This strategy aims to reduce false signals through multi-indicator confirmation.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Signal(Enum):
    """Trade signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NONE = None


@dataclass
class IndicatorValues:
    """Container for indicator values at a point in time"""
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    volume_ma: float
    price: float

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'rsi': self.rsi,
            'macd': self.macd,
            'macd_signal': self.macd_signal,
            'macd_histogram': self.macd_histogram,
            'bb_upper': self.bb_upper,
            'bb_middle': self.bb_middle,
            'bb_lower': self.bb_lower,
            'bb_width': self.bb_width,
            'volume_ma': self.volume_ma,
            'price': self.price
        }


@dataclass
class StrategyConfig:
    """Configuration for multi-indicator strategy"""
    # RSI parameters
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70

    # MACD parameters
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Bollinger Bands parameters
    bb_period: int = 20
    bb_std: float = 2.0

    # Volume parameters
    volume_ma_period: int = 20
    volume_surge_multiplier: float = 1.5

    # Risk management
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0

    # Signal confirmation
    require_all_confirmations: bool = True  # Require all indicators to agree
    min_confirmations: int = 2  # Minimum number of confirming indicators


class MultiIndicatorStrategy:
    """
    Multi-indicator trading strategy combining RSI, MACD, and Bollinger Bands

    Features:
    - Multiple timeframe confirmation
    - Adaptive signal strength scoring
    - Volume confirmation
    - Risk-adjusted position sizing
    """

    def __init__(self, config: StrategyConfig = None):
        """
        Initialize strategy with configuration

        Args:
            config: Strategy configuration (uses defaults if None)
        """
        self.config = config or StrategyConfig()
        logger.info(f"MultiIndicatorStrategy initialized with config: {self.config}")

    def calculate_rsi(self, data: pd.DataFrame, period: int = None) -> pd.Series:
        """
        Calculate RSI (Relative Strength Index)

        Args:
            data: OHLCV DataFrame
            period: RSI period (uses config default if None)

        Returns:
            RSI values as Series
        """
        period = period or self.config.rsi_period
        close = data['close']

        # Calculate price changes
        delta = close.diff()

        # Separate gains and losses
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        # Calculate RS and RSI
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_macd(
        self,
        data: pd.DataFrame,
        fast: int = None,
        slow: int = None,
        signal: int = None
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Args:
            data: OHLCV DataFrame
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period

        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        fast = fast or self.config.macd_fast
        slow = slow or self.config.macd_slow
        signal_period = signal or self.config.macd_signal

        close = data['close']

        # Calculate EMAs
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        # MACD line
        macd_line = ema_fast - ema_slow

        # Signal line
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

        # Histogram
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_bollinger_bands(
        self,
        data: pd.DataFrame,
        period: int = None,
        std_dev: float = None
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands

        Args:
            data: OHLCV DataFrame
            period: Moving average period
            std_dev: Number of standard deviations

        Returns:
            Tuple of (upper_band, middle_band, lower_band, bandwidth)
        """
        period = period or self.config.bb_period
        std_dev = std_dev or self.config.bb_std

        close = data['close']

        # Middle band (SMA)
        middle_band = close.rolling(window=period).mean()

        # Standard deviation
        std = close.rolling(window=period).std()

        # Upper and lower bands
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)

        # Bandwidth (volatility measure)
        bandwidth = (upper_band - lower_band) / middle_band

        return upper_band, middle_band, lower_band, bandwidth

    def calculate_volume_ma(
        self,
        data: pd.DataFrame,
        period: int = None
    ) -> pd.Series:
        """
        Calculate volume moving average

        Args:
            data: OHLCV DataFrame
            period: Moving average period

        Returns:
            Volume MA as Series
        """
        period = period or self.config.volume_ma_period
        return data['volume'].rolling(window=period).mean()

    def calculate_all_indicators(
        self,
        data: pd.DataFrame,
        idx: int
    ) -> Optional[IndicatorValues]:
        """
        Calculate all indicators at a specific index

        Args:
            data: OHLCV DataFrame
            idx: Index position

        Returns:
            IndicatorValues or None if insufficient data
        """
        # Need enough data for all indicators
        min_period = max(
            self.config.rsi_period,
            self.config.macd_slow,
            self.config.bb_period,
            self.config.volume_ma_period
        )

        if idx < min_period:
            return None

        # Get data up to current index
        if isinstance(data.index, pd.DatetimeIndex):
            data_subset = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_subset = data.iloc[:idx+1]

        try:
            # Calculate indicators
            rsi = self.calculate_rsi(data_subset)
            macd_line, signal_line, histogram = self.calculate_macd(data_subset)
            upper_bb, middle_bb, lower_bb, bb_width = self.calculate_bollinger_bands(data_subset)
            volume_ma = self.calculate_volume_ma(data_subset)

            # Get current values
            current_rsi = rsi.iloc[-1]
            current_macd = macd_line.iloc[-1]
            current_signal = signal_line.iloc[-1]
            current_histogram = histogram.iloc[-1]
            current_upper_bb = upper_bb.iloc[-1]
            current_middle_bb = middle_bb.iloc[-1]
            current_lower_bb = lower_bb.iloc[-1]
            current_bb_width = bb_width.iloc[-1]
            current_volume_ma = volume_ma.iloc[-1]
            current_price = data_subset['close'].iloc[-1]

            # Check for NaN values
            if any(pd.isna(val) for val in [
                current_rsi, current_macd, current_signal,
                current_upper_bb, current_middle_bb, current_lower_bb,
                current_volume_ma
            ]):
                return None

            return IndicatorValues(
                rsi=current_rsi,
                macd=current_macd,
                macd_signal=current_signal,
                macd_histogram=current_histogram,
                bb_upper=current_upper_bb,
                bb_middle=current_middle_bb,
                bb_lower=current_lower_bb,
                bb_width=current_bb_width,
                volume_ma=current_volume_ma,
                price=current_price
            )

        except Exception as e:
            logger.warning(f"Error calculating indicators at idx {idx}: {e}")
            return None

    def evaluate_long_signals(
        self,
        indicators: IndicatorValues,
        current_volume: float
    ) -> tuple[bool, int, list[str]]:
        """
        Evaluate conditions for LONG signal

        Args:
            indicators: Current indicator values
            current_volume: Current volume

        Returns:
            Tuple of (signal_valid, confirmation_count, reasons)
        """
        confirmations = 0
        reasons = []

        # 1. RSI oversold
        if indicators.rsi < self.config.rsi_oversold:
            confirmations += 1
            reasons.append(f"RSI oversold ({indicators.rsi:.1f} < {self.config.rsi_oversold})")

        # 2. MACD bullish (histogram positive or about to cross)
        if indicators.macd_histogram > 0 or (
            indicators.macd_histogram > -0.001 and indicators.macd > indicators.macd_signal
        ):
            confirmations += 1
            reasons.append(f"MACD bullish (hist: {indicators.macd_histogram:.4f})")

        # 3. Price near lower Bollinger Band (potential bounce)
        bb_position = (indicators.price - indicators.bb_lower) / (indicators.bb_upper - indicators.bb_lower)
        if bb_position < 0.25:  # In lower 25% of BB range
            confirmations += 1
            reasons.append(f"Price near lower BB ({bb_position:.1%} of range)")

        # 4. Volume surge (confirmation of move)
        if current_volume > indicators.volume_ma * self.config.volume_surge_multiplier:
            confirmations += 1
            reasons.append(f"Volume surge ({current_volume/indicators.volume_ma:.1f}x avg)")

        # Determine if signal is valid
        if self.config.require_all_confirmations:
            signal_valid = confirmations == 4
        else:
            signal_valid = confirmations >= self.config.min_confirmations

        return signal_valid, confirmations, reasons

    def evaluate_short_signals(
        self,
        indicators: IndicatorValues,
        current_volume: float
    ) -> tuple[bool, int, list[str]]:
        """
        Evaluate conditions for SHORT signal

        Args:
            indicators: Current indicator values
            current_volume: Current volume

        Returns:
            Tuple of (signal_valid, confirmation_count, reasons)
        """
        confirmations = 0
        reasons = []

        # 1. RSI overbought
        if indicators.rsi > self.config.rsi_overbought:
            confirmations += 1
            reasons.append(f"RSI overbought ({indicators.rsi:.1f} > {self.config.rsi_overbought})")

        # 2. MACD bearish (histogram negative or about to cross)
        if indicators.macd_histogram < 0 or (
            indicators.macd_histogram < 0.001 and indicators.macd < indicators.macd_signal
        ):
            confirmations += 1
            reasons.append(f"MACD bearish (hist: {indicators.macd_histogram:.4f})")

        # 3. Price near upper Bollinger Band (potential reversal)
        bb_position = (indicators.price - indicators.bb_lower) / (indicators.bb_upper - indicators.bb_lower)
        if bb_position > 0.75:  # In upper 25% of BB range
            confirmations += 1
            reasons.append(f"Price near upper BB ({bb_position:.1%} of range)")

        # 4. Volume surge (confirmation of move)
        if current_volume > indicators.volume_ma * self.config.volume_surge_multiplier:
            confirmations += 1
            reasons.append(f"Volume surge ({current_volume/indicators.volume_ma:.1f}x avg)")

        # Determine if signal is valid
        if self.config.require_all_confirmations:
            signal_valid = confirmations == 4
        else:
            signal_valid = confirmations >= self.config.min_confirmations

        return signal_valid, confirmations, reasons

    def generate_signal(
        self,
        row: pd.Series,
        position: Any,
        idx: int,
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal based on multi-indicator analysis

        Args:
            row: Current row data
            position: Current position (or None)
            idx: Current index
            data: Full OHLCV DataFrame

        Returns:
            Signal dictionary or None
        """
        # Calculate all indicators
        indicators = self.calculate_all_indicators(data, idx)

        if indicators is None:
            return None

        current_volume = row['volume']

        # If no position, look for entry signals
        if position is None:
            # Check for LONG signal
            long_valid, long_count, long_reasons = self.evaluate_long_signals(
                indicators, current_volume
            )

            if long_valid:
                logger.debug(f"LONG signal at idx {idx}: {long_count} confirmations - {', '.join(long_reasons)}")
                return {
                    'action': 'BUY',
                    'stop_loss_pct': self.config.stop_loss_pct,
                    'take_profit_pct': self.config.take_profit_pct,
                    'reason': f"{long_count} confirmations: {', '.join(long_reasons)}",
                    'indicators': indicators.to_dict()
                }

            # Check for SHORT signal
            short_valid, short_count, short_reasons = self.evaluate_short_signals(
                indicators, current_volume
            )

            if short_valid:
                logger.debug(f"SHORT signal at idx {idx}: {short_count} confirmations - {', '.join(short_reasons)}")
                return {
                    'action': 'SELL',
                    'stop_loss_pct': self.config.stop_loss_pct,
                    'take_profit_pct': self.config.take_profit_pct,
                    'reason': f"{short_count} confirmations: {', '.join(short_reasons)}",
                    'indicators': indicators.to_dict()
                }

        # If we have a position, check for exit signals
        else:
            if hasattr(position, 'order_type'):
                # Exit LONG if SHORT signals appear
                if position.order_type.value == 'BUY':
                    short_valid, _, _ = self.evaluate_short_signals(indicators, current_volume)
                    if short_valid:
                        return {'action': 'HOLD'}  # Close position

                # Exit SHORT if LONG signals appear
                elif position.order_type.value == 'SELL':
                    long_valid, _, _ = self.evaluate_long_signals(indicators, current_volume)
                    if long_valid:
                        return {'action': 'HOLD'}  # Close position

        return None


def create_multi_indicator_strategy(
    rsi_period: int = 14,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
    require_all: bool = False,
    min_confirmations: int = 2
):
    """
    Factory function to create multi-indicator strategy with custom parameters

    Args:
        rsi_period: RSI period
        rsi_oversold: RSI oversold threshold
        rsi_overbought: RSI overbought threshold
        macd_fast: MACD fast EMA period
        macd_slow: MACD slow EMA period
        macd_signal: MACD signal period
        bb_period: Bollinger Bands period
        bb_std: Bollinger Bands standard deviation
        require_all: Require all 4 confirmations (strict mode)
        min_confirmations: Minimum confirmations needed (if not require_all)

    Returns:
        Strategy function compatible with backtest engine
    """
    config = StrategyConfig(
        rsi_period=rsi_period,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        bb_period=bb_period,
        bb_std=bb_std,
        require_all_confirmations=require_all,
        min_confirmations=min_confirmations
    )

    strategy = MultiIndicatorStrategy(config)

    return strategy.generate_signal
