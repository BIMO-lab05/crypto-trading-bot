#!/usr/bin/env python3
"""
Mean Reversion Strategy
Phase 2.2 - Alternative Strategy Approach

Strategy Logic:
- BUY when price touches/breaks below lower Bollinger Band + RSI oversold
- SELL when price touches/breaks above upper Bollinger Band + RSI overbought
- EXIT at middle band (mean) or stop loss

This strategy assumes price will revert to mean after extreme moves.
Better suited for ranging/choppy markets vs trend-following.

Key Differences from Trend Strategies:
1. Fades extremes instead of following them
2. Faster profit targets (mean reversion is quick)
3. Tighter stops (bounces can fail)
4. Works in sideways markets
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MeanReversionConfig:
    """Configuration for mean reversion strategy"""
    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0
    bb_entry_threshold: float = 0.05  # How far beyond band to trigger (5% of width)

    # RSI confirmation
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    require_rsi_confirmation: bool = True

    # Risk management
    stop_loss_pct: float = 1.5  # Tighter than trend strategies
    take_profit_pct: float = 2.0  # Smaller target (quick bounce)

    # Exit options
    exit_at_mean: bool = True  # Close position when price reaches middle band
    exit_on_opposite_band: bool = False  # Close when opposite band hit


class MeanReversionStrategy:
    """
    Mean reversion strategy using Bollinger Bands

    Entry Rules:
    - LONG: Price <= Lower BB AND RSI < oversold
    - SHORT: Price >= Upper BB AND RSI > overbought

    Exit Rules:
    - Target: Middle band (mean) or take profit %
    - Stop: Stop loss % or opposite extreme
    """

    def __init__(self, config: MeanReversionConfig = None):
        """Initialize strategy with configuration"""
        self.config = config or MeanReversionConfig()
        logger.info(f"MeanReversionStrategy initialized: BB({self.config.bb_period},{self.config.bb_std}), "
                   f"RSI({self.config.rsi_period}), SL:{self.config.stop_loss_pct}%, TP:{self.config.take_profit_pct}%")

    def calculate_rsi(self, data: pd.DataFrame, period: int = None) -> pd.Series:
        """Calculate RSI"""
        period = period or self.config.rsi_period
        close = data['close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_bollinger_bands(
        self,
        data: pd.DataFrame,
        period: int = None,
        std_dev: float = None
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        period = period or self.config.bb_period
        std_dev = std_dev or self.config.bb_std

        close = data['close']
        middle_band = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)

        return upper_band, middle_band, lower_band

    def is_at_lower_band(
        self,
        price: float,
        lower_band: float,
        upper_band: float,
        middle_band: float
    ) -> bool:
        """Check if price is at or below lower Bollinger Band"""
        band_width = upper_band - lower_band
        threshold = lower_band + (band_width * self.config.bb_entry_threshold)
        return price <= threshold

    def is_at_upper_band(
        self,
        price: float,
        upper_band: float,
        lower_band: float,
        middle_band: float
    ) -> bool:
        """Check if price is at or above upper Bollinger Band"""
        band_width = upper_band - lower_band
        threshold = upper_band - (band_width * self.config.bb_entry_threshold)
        return price >= threshold

    def is_at_middle_band(
        self,
        price: float,
        middle_band: float,
        tolerance_pct: float = 0.3
    ) -> bool:
        """Check if price has reverted to mean (middle band)"""
        tolerance = middle_band * (tolerance_pct / 100)
        return abs(price - middle_band) <= tolerance

    def generate_signal(
        self,
        row: pd.Series,
        position: Any,
        idx: int,
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Generate mean reversion trading signal

        Args:
            row: Current row data
            position: Current position (or None)
            idx: Current index
            data: Full OHLCV DataFrame

        Returns:
            Signal dictionary or None
        """
        # Need enough data for indicators
        min_period = max(self.config.bb_period, self.config.rsi_period)

        if idx < min_period:
            return None

        # Get data subset
        if isinstance(data.index, pd.DatetimeIndex):
            data_subset = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_subset = data.iloc[:idx+1]

        try:
            # Calculate indicators
            rsi = self.calculate_rsi(data_subset)
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(data_subset)

            # Current values
            current_price = row['close']
            current_rsi = rsi.iloc[-1]
            current_upper = upper_bb.iloc[-1]
            current_middle = middle_bb.iloc[-1]
            current_lower = lower_bb.iloc[-1]

            # Check for NaN
            if any(pd.isna(val) for val in [current_rsi, current_upper, current_middle, current_lower]):
                return None

            # If no position, look for entry signals
            if position is None:
                # LONG entry: Price at lower band + RSI oversold
                at_lower = self.is_at_lower_band(current_price, current_lower, current_upper, current_middle)
                rsi_oversold = current_rsi < self.config.rsi_oversold

                if at_lower and (rsi_oversold or not self.config.require_rsi_confirmation):
                    reason = f"Mean reversion LONG: Price ${current_price:.2f} at lower BB ${current_lower:.2f}, RSI {current_rsi:.1f}"
                    logger.debug(f"Signal at idx {idx}: {reason}")

                    return {
                        'action': 'BUY',
                        'stop_loss_pct': self.config.stop_loss_pct,
                        'take_profit_pct': self.config.take_profit_pct,
                        'reason': reason,
                        'price': current_price,
                        'lower_bb': current_lower,
                        'middle_bb': current_middle,
                        'upper_bb': current_upper,
                        'rsi': current_rsi
                    }

                # SHORT entry: Price at upper band + RSI overbought
                at_upper = self.is_at_upper_band(current_price, current_upper, current_lower, current_middle)
                rsi_overbought = current_rsi > self.config.rsi_overbought

                if at_upper and (rsi_overbought or not self.config.require_rsi_confirmation):
                    reason = f"Mean reversion SHORT: Price ${current_price:.2f} at upper BB ${current_upper:.2f}, RSI {current_rsi:.1f}"
                    logger.debug(f"Signal at idx {idx}: {reason}")

                    return {
                        'action': 'SELL',
                        'stop_loss_pct': self.config.stop_loss_pct,
                        'take_profit_pct': self.config.take_profit_pct,
                        'reason': reason,
                        'price': current_price,
                        'lower_bb': current_lower,
                        'middle_bb': current_middle,
                        'upper_bb': current_upper,
                        'rsi': current_rsi
                    }

            # If we have a position, check for exit signals
            else:
                if hasattr(position, 'order_type'):
                    # Exit LONG at middle band (mean reversion complete)
                    if position.order_type.value == 'BUY':
                        if self.config.exit_at_mean and self.is_at_middle_band(current_price, current_middle):
                            logger.debug(f"Exit LONG at idx {idx}: Price reverted to mean ${current_middle:.2f}")
                            return {'action': 'HOLD'}  # Close position

                        # Exit if price hits upper band (opposite extreme)
                        if self.config.exit_on_opposite_band and self.is_at_upper_band(
                            current_price, current_upper, current_lower, current_middle
                        ):
                            logger.debug(f"Exit LONG at idx {idx}: Price hit upper band ${current_upper:.2f}")
                            return {'action': 'HOLD'}

                    # Exit SHORT at middle band (mean reversion complete)
                    elif position.order_type.value == 'SELL':
                        if self.config.exit_at_mean and self.is_at_middle_band(current_price, current_middle):
                            logger.debug(f"Exit SHORT at idx {idx}: Price reverted to mean ${current_middle:.2f}")
                            return {'action': 'HOLD'}

                        # Exit if price hits lower band (opposite extreme)
                        if self.config.exit_on_opposite_band and self.is_at_lower_band(
                            current_price, current_lower, current_upper, current_middle
                        ):
                            logger.debug(f"Exit SHORT at idx {idx}: Price hit lower band ${current_lower:.2f}")
                            return {'action': 'HOLD'}

            return None

        except Exception as e:
            logger.warning(f"Error generating signal at idx {idx}: {e}")
            return None


def create_mean_reversion_strategy(
    bb_period: int = 20,
    bb_std: float = 2.0,
    bb_entry_threshold: float = 0.05,
    rsi_period: int = 14,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    require_rsi: bool = True,
    stop_loss_pct: float = 1.5,
    take_profit_pct: float = 2.0,
    exit_at_mean: bool = True,
    exit_on_opposite: bool = False
):
    """
    Factory function to create mean reversion strategy

    Args:
        bb_period: Bollinger Bands period
        bb_std: Bollinger Bands standard deviation
        bb_entry_threshold: How far beyond band to trigger (fraction of width)
        rsi_period: RSI period
        rsi_oversold: RSI oversold threshold
        rsi_overbought: RSI overbought threshold
        require_rsi: Require RSI confirmation for entries
        stop_loss_pct: Stop loss percentage
        take_profit_pct: Take profit percentage
        exit_at_mean: Exit when price reaches middle band
        exit_on_opposite: Exit when price reaches opposite band

    Returns:
        Strategy function compatible with backtest engine
    """
    config = MeanReversionConfig(
        bb_period=bb_period,
        bb_std=bb_std,
        bb_entry_threshold=bb_entry_threshold,
        rsi_period=rsi_period,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        require_rsi_confirmation=require_rsi,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        exit_at_mean=exit_at_mean,
        exit_on_opposite_band=exit_on_opposite
    )

    strategy = MeanReversionStrategy(config)

    return strategy.generate_signal
